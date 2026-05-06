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
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session, get_db
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
from app.services.nas_search.embedder import embed_passages, embed_query
from app.services.nas_search.indexer import build_filename_header

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
            await run_indexing(full_rescan=body.full_rescan, subdir=body.subdir)
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


@router.post(
    "/index/backfill_filenames",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin)],
)
async def start_filename_backfill(
    background_tasks: BackgroundTasks,
) -> NasIndexRunResponse:
    """v0.6.7 — 모든 nas_files에 파일명 청크(chunk_index=-1) 1개를 추가/갱신.

    본문 인덱싱은 건드리지 않고 파일명+상대경로 단일 청크만 처리.
    이미 존재하는 chunk_index=-1은 새 임베딩으로 덮어쓰기 (idempotent).
    분당 약 100~200개 처리 예상 (12,050개 → 1~2시간).
    """
    if is_indexing():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="인덱싱 또는 backfill이 이미 진행 중입니다",
        )

    async def _runner() -> None:
        try:
            await _run_filename_backfill()
        except Exception:  # noqa: BLE001
            logger.exception("파일명 backfill 실패")

    background_tasks.add_task(_runner)
    started_at = datetime.now(tz=timezone.utc)
    INDEX_PROGRESS.running = True
    INDEX_PROGRESS.started_at = started_at
    INDEX_PROGRESS.current_path = "(backfill_filenames)"
    return NasIndexRunResponse(task_id=started_at.isoformat(), status="running")


async def _run_filename_backfill() -> None:
    """모든 nas_files를 순회. chunk_index=-1 파일명 청크 추가/갱신."""
    async with async_session() as db:
        files = (await db.execute(select(NasFile))).scalars().all()

    INDEX_PROGRESS.reset(total=len(files))
    INDEX_PROGRESS.current_path = "(backfill_filenames)"
    logger.info("파일명 backfill 시작 — 대상 %d개", len(files))

    try:
        for f in files:
            try:
                content = build_filename_header(f.name, f.path, settings.nas_mount_path)
                if not content or content == "()":
                    INDEX_PROGRESS.processed += 1
                    continue
                vec = await asyncio.to_thread(embed_passages, [content])
                async with async_session() as db2:
                    await db2.execute(
                        delete(NasTextChunk).where(
                            NasTextChunk.file_id == f.id,
                            NasTextChunk.chunk_index == -1,
                        )
                    )
                    db2.add(
                        NasTextChunk(
                            file_id=f.id,
                            chunk_index=-1,
                            content=content,
                            embedding=vec[0].tolist(),
                            token_count=len(content),
                        )
                    )
                    await db2.commit()
            except Exception as exc:  # noqa: BLE001
                INDEX_PROGRESS.errors += 1
                INDEX_PROGRESS.last_error = f"{f.path}: {exc}"
                logger.exception("backfill 실패: %s", f.path)
            finally:
                INDEX_PROGRESS.processed += 1
                INDEX_PROGRESS.current_path = f.path
    finally:
        INDEX_PROGRESS.finish()
        logger.info(
            "파일명 backfill 종료 — 처리 %d/%d, 실패 %d",
            INDEX_PROGRESS.processed,
            INDEX_PROGRESS.total,
            INDEX_PROGRESS.errors,
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

    # cosine distance를 distance 컬럼으로 받는다. 점수는 (1 - distance) + 파일명 가산점.
    distance = NasTextChunk.embedding.cosine_distance(query_vec.tolist()).label("distance")
    # v0.6.7 하이브리드 검색: 파일명 ILIKE 매칭 시 +0.2 가산점.
    name_bonus = case(
        (NasFile.name.ilike(f"%{body.query}%"), 0.2),
        else_=0.0,
    ).label("name_bonus")
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
            name_bonus,
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
            score=float((1.0 - row.distance) + (row.name_bonus or 0.0)),
            snippet=_build_snippet(row.content or ""),
        )
        if len(seen) >= body.limit:
            break

    # 가산점 적용 후 재정렬 (파일명 매치된 결과를 상위로).
    sorted_hits = sorted(seen.values(), key=lambda h: h.score, reverse=True)
    return NasSearchResponse(results=sorted_hits)


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
