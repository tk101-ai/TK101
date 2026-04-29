"""NAS 자료 검색 라우터 (v0.6.0 PoC).

엔드포인트:
- GET  /api/nas/status            마운트/인덱스 상태 (전 직원)
- POST /api/nas/index/run         인덱싱 시작 (관리자)
- GET  /api/nas/index/status      인덱싱 진행률 (전 직원)
- POST /api/nas/search/text       텍스트 의미 검색 (전 직원)
- GET  /api/nas/files/{id}/download   원본 다운로드 (전 직원)
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import require_admin, require_module
from app.models.nas_file import NasFile, NasTextChunk
from app.modules.constants import Module
from app.schemas.nas_file import (
    NasIndexProgress,
    NasIndexRunRequest,
    NasIndexRunResponse,
    NasSearchHit,
    NasSearchRequest,
    NasSearchResponse,
    NasStatus,
)
from app.services.nas_search import INDEX_PROGRESS, is_indexing, run_indexing
from app.services.nas_search.embedder import embed_query

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/nas",
    tags=["nas"],
    dependencies=[Depends(require_module(Module.NAS_SEARCH.value))],
)

SNIPPET_CHARS = 200


def _mount_ok(path: str) -> bool:
    """NAS 마운트가 디렉토리이고 읽기 가능한지 확인."""
    return os.path.isdir(path) and os.access(path, os.R_OK)


@router.get("/status", response_model=NasStatus)
async def get_status(db: AsyncSession = Depends(get_db)) -> NasStatus:
    total_q = await db.execute(select(func.count(NasFile.id)))
    indexed_q = await db.execute(
        select(func.count(NasFile.id)).where(NasFile.indexed_at.is_not(None))
    )
    last_q = await db.execute(select(func.max(NasFile.indexed_at)))
    return NasStatus(
        mount_ok=_mount_ok(settings.nas_mount_path),
        mount_path=settings.nas_mount_path,
        total_files=int(total_q.scalar() or 0),
        indexed_files=int(indexed_q.scalar() or 0),
        last_indexed_at=last_q.scalar(),
    )


@router.post(
    "/index/run",
    response_model=NasIndexRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin)],
)
async def start_indexing(
    background_tasks: BackgroundTasks,
    body: NasIndexRunRequest = NasIndexRunRequest(),
) -> NasIndexRunResponse:
    """백그라운드 인덱싱 시작. 진행 중이면 409.

    body는 옵션(빈 요청 허용). full_rescan=True면 file_hash 무관 전체 재인덱싱.
    """
    if is_indexing():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 인덱싱이 진행 중입니다",
        )
    if not _mount_ok(settings.nas_mount_path):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"NAS 마운트를 읽을 수 없습니다: {settings.nas_mount_path}",
        )

    async def _runner() -> None:
        try:
            await run_indexing(full_rescan=body.full_rescan)
        except Exception:  # noqa: BLE001
            logger.exception("NAS 인덱싱 백그라운드 태스크 실패")

    background_tasks.add_task(_runner)
    started_at = datetime.now(tz=timezone.utc)
    INDEX_PROGRESS.running = True
    INDEX_PROGRESS.started_at = started_at
    # task_id는 단일 워커 프로세스 가정의 임시 식별자(타임스탬프).
    return NasIndexRunResponse(
        task_id=started_at.isoformat(),
        status="running",
    )


@router.get("/index/status", response_model=NasIndexProgress)
async def get_index_status() -> NasIndexProgress:
    return NasIndexProgress(
        running=INDEX_PROGRESS.running,
        processed=INDEX_PROGRESS.processed,
        total=INDEX_PROGRESS.total,
        current_path=INDEX_PROGRESS.current_path,
        errors=INDEX_PROGRESS.errors,
        started_at=INDEX_PROGRESS.started_at,
        finished_at=INDEX_PROGRESS.finished_at,
        last_error=INDEX_PROGRESS.last_error,
    )


def _build_snippet(content: str) -> str:
    if not content:
        return ""
    return content[:SNIPPET_CHARS]


@router.post("/search/text", response_model=NasSearchResponse)
async def search_text(
    body: NasSearchRequest,
    db: AsyncSession = Depends(get_db),
) -> NasSearchResponse:
    """텍스트 임베딩 → pgvector cosine 유사도 검색.

    파일 단위로 그룹핑해서 같은 문서에서 가장 점수 좋은 청크 1개만 대표로 반환.
    """
    try:
        query_vec = await asyncio.to_thread(embed_query, body.query)
    except Exception as exc:  # noqa: BLE001
        logger.exception("쿼리 임베딩 실패")
        raise HTTPException(status_code=500, detail=f"쿼리 임베딩 실패: {exc}")

    # cosine distance를 distance 컬럼으로 받는다. 점수는 1 - distance.
    distance = NasTextChunk.embedding.cosine_distance(query_vec.tolist()).label("distance")
    over_limit = body.limit * 5  # 파일 그룹핑 손실 보정

    stmt = (
        select(
            NasFile.id,
            NasFile.path,
            NasFile.name,
            NasFile.file_type,
            NasFile.mime_type,
            NasFile.size_bytes,
            NasFile.mtime,
            NasTextChunk.content,
            distance,
        )
        .join(NasTextChunk, NasTextChunk.file_id == NasFile.id)
        .order_by(distance.asc())
        .limit(over_limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    seen: dict[str, NasSearchHit] = {}
    for row in rows:
        path = row.path
        if path in seen:
            continue
        seen[path] = NasSearchHit(
            id=row.id,
            path=path,
            name=row.name,
            file_type=row.file_type,
            mime_type=row.mime_type,
            size=row.size_bytes,
            mtime=row.mtime,
            score=float(1.0 - row.distance),
            snippet=_build_snippet(row.content or ""),
        )
        if len(seen) >= body.limit:
            break

    return NasSearchResponse(results=list(seen.values()))


def _is_path_within_root(target: str, root: str) -> bool:
    """target의 realpath가 root 디렉토리 안인지 확인. path traversal 방어."""
    try:
        target_real = os.path.realpath(target)
        root_real = os.path.realpath(root)
    except OSError:
        return False
    # commonpath는 다른 드라이브에서 ValueError를 던질 수 있음.
    try:
        return os.path.commonpath([target_real, root_real]) == root_real
    except ValueError:
        return False


@router.get("/files/{file_id}/download")
async def download_file(
    file_id: str,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    result = await db.execute(select(NasFile).where(NasFile.id == file_id))
    nas_file = result.scalar_one_or_none()
    if nas_file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="파일을 찾을 수 없습니다")

    if not _is_path_within_root(nas_file.path, settings.nas_mount_path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="허용되지 않은 경로",
        )
    if not os.path.isfile(nas_file.path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="원본 파일이 NAS에 존재하지 않습니다",
        )
    return FileResponse(
        path=nas_file.path,
        filename=nas_file.name or os.path.basename(nas_file.path),
        media_type=nas_file.mime_type or "application/octet-stream",
    )
