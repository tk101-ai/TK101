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
    NasTopFoldersResponse,
)
from app.services.nas_search import (
    INDEX_PROGRESS,
    SUMMARY_PROGRESS,
    is_indexing,
    is_summarizing,
    run_indexing,
)
from app.services.nas_search.embedder import embed_passages, embed_query
from app.services.nas_search.indexer import build_filename_header
from app.services.nas_search.summarizer import summarize_document

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/nas",
    tags=["nas"],
    dependencies=[Depends(require_module(Module.NAS_SEARCH.value))],
)

SNIPPET_CHARS = 200

# file_kinds → mime_type(들) 매핑. v0.7.0부터 한글/엑셀 추가.
# hwp는 HWP5(application/x-hwp)와 HWPX(application/vnd.hancom.hwpx) 두 MIME을 모두 매칭.
# 단일 string 또는 tuple[str, ...] 모두 허용 (아래 _flatten_kind_mimes에서 평탄화).
FILE_KIND_MIME_MAP: dict[str, str | tuple[str, ...]] = {
    "pdf": "application/pdf",
    "word": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "ppt": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "hwp": ("application/x-hwp", "application/vnd.hancom.hwpx"),
    "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _flatten_kind_mimes(kinds: list[str]) -> list[str]:
    """file_kinds 리스트를 SQL IN 절에 들어갈 mime_type 평탄 리스트로 변환.

    예: ["pdf", "hwp"] → ["application/pdf", "application/x-hwp", "application/vnd.hancom.hwpx"]
    알 수 없는 kind는 무시.
    """
    out: list[str] = []
    for kind in kinds:
        mapped = FILE_KIND_MIME_MAP.get(kind)
        if mapped is None:
            continue
        if isinstance(mapped, tuple):
            out.extend(mapped)
        else:
            out.append(mapped)
    return out


def _mount_ok(path: str) -> bool:
    """NAS 마운트가 디렉토리이고 읽기 가능한지 확인."""
    return os.path.isdir(path) and os.access(path, os.R_OK)


def _resolve_path_prefix(relative: str, root: str) -> str:
    """상대 경로 prefix를 NAS root와 join 후 정규화.

    path traversal(`..`, 절대경로 등)을 차단하기 위해 결과가 root 밖으로
    벗어나면 ValueError를 발생시킨다. 반환값은 절대경로 prefix.
    """
    candidate = os.path.normpath(os.path.join(root, relative))
    root_norm = os.path.normpath(root)
    # commonpath는 다른 드라이브에서 ValueError를 던질 수 있다 → 그대로 위임.
    if os.path.commonpath([candidate, root_norm]) != root_norm:
        raise ValueError("경로가 NAS 루트 밖입니다")
    return candidate


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


# v0.7.x — Claude Haiku 4.5 기반 한국어 키워드 요약 backfill ----------------------
# chunk_index=-2 청크로 임베딩 저장. 본 인덱싱(INDEX_PROGRESS)과 분리된 별도 진행률.
# Anthropic API 호출이 자원 충돌 없이 본 인덱싱과 동시 실행 가능.

# 요약 backfill 동시성 — 동시 호출 수. 너무 높이면 Anthropic rate limit 걸림.
SUMMARY_CONCURRENCY = 3
# 본문 텍스트가 너무 짧으면(파일명만 있는 경우 등) skip.
SUMMARY_MIN_TEXT_CHARS = 30


@router.post(
    "/index/backfill_summaries",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_admin)],
)
async def start_summary_backfill(
    background_tasks: BackgroundTasks,
) -> NasIndexRunResponse:
    """v0.7.x — 모든 nas_files에 키워드 요약 청크(chunk_index=-2)를 추가/갱신.

    Claude Haiku 4.5 호출로 100~200자 한국어 키워드 요약을 생성해
    본문/파일명 청크와 함께 cosine 매칭되도록 임베딩 저장.

    비용 추산: 12K 파일 × Haiku 4.5 ≈ $15~20.
    본 인덱싱과 별도 진행률(SUMMARY_PROGRESS) 사용 → 동시 실행 가능.
    """
    if is_summarizing():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이미 요약 backfill이 진행 중입니다",
        )
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANTHROPIC_API_KEY가 설정되지 않았습니다",
        )

    async def _runner() -> None:
        try:
            await _run_summary_backfill()
        except Exception:  # noqa: BLE001
            logger.exception("요약 backfill 실패")

    background_tasks.add_task(_runner)
    started_at = datetime.now(tz=timezone.utc)
    SUMMARY_PROGRESS.running = True
    SUMMARY_PROGRESS.started_at = started_at
    SUMMARY_PROGRESS.current_path = "(backfill_summaries)"
    return NasIndexRunResponse(task_id=started_at.isoformat(), status="running")


@router.get("/index/summary_status", response_model=NasIndexProgress)
async def get_summary_status() -> NasIndexProgress:
    return NasIndexProgress(
        running=SUMMARY_PROGRESS.running,
        processed=SUMMARY_PROGRESS.processed,
        total=SUMMARY_PROGRESS.total,
        current_path=SUMMARY_PROGRESS.current_path,
        errors=SUMMARY_PROGRESS.errors,
        started_at=SUMMARY_PROGRESS.started_at,
        finished_at=SUMMARY_PROGRESS.finished_at,
        last_error=SUMMARY_PROGRESS.last_error,
    )


async def _load_file_text(file_id) -> str:
    """파일의 본문 청크(chunk_index >= 0)를 join. -1/-2 메타 청크 제외."""
    async with async_session() as db:
        result = await db.execute(
            select(NasTextChunk.content)
            .where(
                NasTextChunk.file_id == file_id,
                NasTextChunk.chunk_index >= 0,
            )
            .order_by(NasTextChunk.chunk_index.asc())
        )
        contents = [row[0] for row in result.all() if row[0]]
    return "\n\n".join(contents)


async def _process_one_summary(file: NasFile, semaphore: asyncio.Semaphore) -> None:
    """파일 1건 요약 + 임베딩 + DB upsert. 실패 시 SUMMARY_PROGRESS.errors++."""
    async with semaphore:
        SUMMARY_PROGRESS.current_path = file.path
        try:
            text = await _load_file_text(file.id)
            if not text or len(text.strip()) < SUMMARY_MIN_TEXT_CHARS:
                # 본문 짧으면 요약 가치 낮음 → skip.
                return

            summary = await summarize_document(text, file.name or "")
            if not summary:
                return

            # 임베딩은 동기 CPU 작업 → 스레드.
            vec = await asyncio.to_thread(embed_passages, [summary])
            async with async_session() as db:
                await db.execute(
                    delete(NasTextChunk).where(
                        NasTextChunk.file_id == file.id,
                        NasTextChunk.chunk_index == -2,
                    )
                )
                db.add(
                    NasTextChunk(
                        file_id=file.id,
                        chunk_index=-2,
                        content=summary,
                        embedding=vec[0].tolist(),
                        token_count=len(summary),
                    )
                )
                await db.commit()
        except Exception as exc:  # noqa: BLE001
            SUMMARY_PROGRESS.errors += 1
            SUMMARY_PROGRESS.last_error = f"{file.path}: {exc}"
            SUMMARY_PROGRESS.failures.append(SUMMARY_PROGRESS.last_error)
            logger.exception("요약 backfill 실패: %s", file.path)
        finally:
            SUMMARY_PROGRESS.processed += 1


async def _run_summary_backfill() -> None:
    """모든 nas_files 순회 — Haiku 4.5 요약 → chunk_index=-2 청크 upsert.

    동시성은 SUMMARY_CONCURRENCY로 제한 (Anthropic rate limit 보호).
    실패해도 다음 파일로 진행. 본 인덱싱(INDEX_PROGRESS)과 분리된 진행률 사용.
    """
    async with async_session() as db:
        files = (await db.execute(select(NasFile))).scalars().all()

    SUMMARY_PROGRESS.reset(total=len(files))
    SUMMARY_PROGRESS.current_path = "(backfill_summaries)"
    logger.info(
        "요약 backfill 시작 — 대상 %d개 (동시성=%d)",
        len(files),
        SUMMARY_CONCURRENCY,
    )

    semaphore = asyncio.Semaphore(SUMMARY_CONCURRENCY)
    try:
        # gather로 묶되 semaphore가 실제 동시성을 제한.
        await asyncio.gather(
            *(_process_one_summary(f, semaphore) for f in files),
            return_exceptions=True,
        )
    finally:
        SUMMARY_PROGRESS.finish()
        logger.info(
            "요약 backfill 종료 — 처리 %d/%d, 실패 %d",
            SUMMARY_PROGRESS.processed,
            SUMMARY_PROGRESS.total,
            SUMMARY_PROGRESS.errors,
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
    )

    # 필터 적용 — None인 필드는 건너뛴다(회귀 없음).
    if body.file_kinds:
        # hwp는 두 MIME(hwp + hwpx)으로 평탄화되므로 일반 리스트 컴프리헨션 대신 헬퍼 사용.
        mimes = _flatten_kind_mimes(list(body.file_kinds))
        if mimes:
            stmt = stmt.where(NasFile.mime_type.in_(mimes))

    if body.path_prefix:
        try:
            absolute_prefix = _resolve_path_prefix(
                body.path_prefix, settings.nas_mount_path
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"잘못된 path_prefix: {exc}",
            )
        stmt = stmt.where(NasFile.path.startswith(absolute_prefix))

    if body.mtime_from is not None:
        stmt = stmt.where(NasFile.mtime >= body.mtime_from)
    if body.mtime_to is not None:
        stmt = stmt.where(NasFile.mtime <= body.mtime_to)

    stmt = stmt.order_by(distance.asc()).limit(over_limit)
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


@router.get("/folders/top", response_model=NasTopFoldersResponse)
async def list_top_folders(
    db: AsyncSession = Depends(get_db),
) -> NasTopFoldersResponse:
    """NAS_MOUNT_PATH 직하 1단계 폴더만 distinct로 모아 반환.

    nas_files.path는 절대 경로이므로 root prefix를 떼고 첫 세그먼트만 추출한다.
    파일 12K 정도 규모는 Python set 처리로 충분.
    """
    root = os.path.normpath(settings.nas_mount_path)
    rows = (await db.execute(select(NasFile.path))).scalars().all()

    folders: set[str] = set()
    for path in rows:
        if not path:
            continue
        normalized = os.path.normpath(path)
        try:
            relative = os.path.relpath(normalized, root)
        except ValueError:
            # 다른 드라이브 등으로 relpath 계산 불가한 경우 skip.
            continue
        if relative.startswith("..") or relative in (".", ""):
            continue
        # OS별 separator 차이를 흡수.
        first_segment = relative.replace("\\", "/").split("/", 1)[0].strip()
        if first_segment:
            folders.add(first_segment)

    return NasTopFoldersResponse(folders=sorted(folders))


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
