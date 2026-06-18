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
import uuid
from datetime import datetime, timezone

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session, get_db
from app.dependencies import get_current_user, require_admin, require_module
from app.models.nas_file import NasFile, NasTextChunk
from app.models.user import User
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
from app.services.nas_search.embedder import embed_passages
from app.services.nas_search.hybrid import (
    DEFAULT_RRF_K as RRF_K,
    reciprocal_rank_fusion,
    tokenize_query,
)
from app.services.nas_search.indexer import build_filename_header
from app.services.nas_search.query_embedder import embed_query as embed_query_vec
from app.services.nas_search.romanize import has_hangul, romanize_hangul
from app.services.nas_search.qdrant_search import (
    build_qdrant_filter,
    keyword_arm,
    vector_arm,
)
from app.services.nas_search.summarizer import summarize_document

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


def _indexing_disabled() -> None:
    """인앱 인덱싱/backfill 비활성(deprecated).

    이 경로들은 레거시 e5(1024-dim)→pgvector(nas_text_chunks)에 적재하는데, 현재 검색은
    Qwen3(2560-dim)→Qdrant docs_text 단일 소스라 **여기서 만든 임베딩은 검색에 보이지 않는다**
    (죽은 데이터 + backfill_summaries는 Haiku 비용까지 발생). 실제 적재는 외부 파이프라인
    /home/ubuntu/tk101-rag 가 담당. 프론트 인덱싱 UI도 제거됨. 혼선·비용 방지를 위해 비활성.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "인앱 인덱싱/backfill 은 비활성화되었습니다(레거시 e5/pgvector — 검색 미반영). "
            "임베딩 적재는 tk101-rag 파이프라인(Qwen3/Qdrant)을 사용하세요."
        ),
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
    """[deprecated/410] 레거시 e5/pgvector 인덱싱 — 검색 미반영이라 비활성."""
    _indexing_disabled()
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
    [deprecated/410] 레거시 e5/pgvector — 검색 미반영이라 비활성.
    """
    _indexing_disabled()
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
    [deprecated/410] 레거시 e5/pgvector — 검색 미반영인데 Haiku 비용만 발생해 비활성.
    """
    _indexing_disabled()
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


# 파일 그룹핑으로 손실되는 후보를 보정하기 위한 over-fetch 배수.
OVERFETCH_MULTIPLIER = 5

# 키워드 매칭을 '고신뢰(0.85, 관련도 게이트 면제)'로 인정하는 최소 매칭 토큰 수.
# 다토큰 질의에서 흔한 토큰(시간/이벤트/정리 등) 1개만 substring 매칭돼도
# 0.85로 게이트를 우회하던 노이즈를 막는다(단일어 질의는 1로 완화 — 품번·엔티티
# 정확검색 보존). 질의 토큰 수와 min 으로 결합해 적용.
KW_STRONG_MIN_MATCH = 2


def _keyword_is_strong(pl_k: dict, min_match: int) -> bool:
    """키워드 매칭이 0.85 고신뢰를 받을 만큼 '강한가'.

    - 매칭 토큰 수 >= min_match 면 강함(다토큰 질의는 여러 어절이 실제로 등장).
    - 또는 매칭 토큰 중 '구체적'(숫자 포함=품번/날짜, 또는 5자 이상 고유어)이
      하나라도 있으면 강함(단일 품번·고객사명 정확검색 보존).
    약매칭(흔한 토큰 1개)은 벡터 관련도 게이트로 강등 → 노이즈 차단.
    """
    matched = pl_k.get("_matched_tokens") or []
    if len(matched) >= min_match:
        return True
    return any(any(c.isdigit() for c in t) or len(t) >= 5 for t in matched)

# Qdrant payload에는 nas_files의 mime_type/size/mtime/UUID가 없다. 응답 스키마는
# 유지하되(프론트 계약 불변) Qdrant로 채울 수 있는 것만 채우고 나머지는 null.
# - id: NasSearchHit.id는 UUID 필수라 doc_id(16hex)를 결정론적 UUID로 변환해 채움.
# - name: payload엔 없으므로 path basename으로 채움.
# - mime_type: source_type → mime 역매핑(가능한 것만), 없으면 null.
# - size/mtime: Qdrant에 없어 null.
_SOURCE_TYPE_TO_MIME: dict[str, str] = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "hwp": "application/x-hwp",
    "hwpx": "application/vnd.hancom.hwpx",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _doc_id_to_uuid(doc_id: str) -> uuid.UUID:
    """Qdrant doc_id(임의 문자열)를 결정론적 UUID5로 변환(스키마 id 채움용).

    NasSearchHit.id는 UUID 필수. Qdrant엔 nas_files UUID가 없으므로 doc_id에서
    안정적으로 파생한다(같은 문서는 항상 같은 UUID). 다운로드는 path 기반이라
    이 UUID로 nas_files를 조회하지 않는다.
    """
    return uuid.uuid5(uuid.NAMESPACE_URL, f"nas-doc:{doc_id}")


def _resolve_dept_scope(user: User) -> list[str] | None:
    """부서 스코핑 → Qdrant dept 라벨 리스트(또는 None=전체검색).

    - 기능 OFF(nas_dept_scoping_enabled=False) → None(전체).
    - 전체검색 허용 role(admin 등) → None(전체).
    - 사용자 부서가 DOC_DEPT_BY_USER_DEPT에 매핑되면 그 라벨들로 한정.
    - 매핑 없으면 보수적으로 None(전체) — 기능을 막지 않기 위함.
    """
    if not settings.nas_dept_scoping_enabled:
        return None
    if (user.role or "") in settings.nas_full_search_role_set:
        return None
    labels = settings.DOC_DEPT_BY_USER_DEPT.get(user.department or "")
    return labels or None


@router.post("/search/text", response_model=NasSearchResponse)
async def search_text(
    body: NasSearchRequest,
    user: User = Depends(get_current_user),
) -> NasSearchResponse:
    """하이브리드 검색 — 의미검색(벡터) + 정확검색(키워드)을 RRF로 결합.

    데이터 소스는 Qdrant docs_text 단일 소스. 두 arm 모두 Qdrant를 조회하고
    결합 키는 doc_id다.
    - 벡터 arm: Qwen3-Embedding-4B 쿼리 임베딩 → Qdrant cosine 유사도.
    - 키워드 arm: payload text/path 토큰 substring 매칭(품번·고유명사 정확 매칭).
    두 순위를 RRF로 합쳐 doc_id 단위로 대표 청크 1개만 반환한다.
    """
    try:
        query_vec = await asyncio.to_thread(embed_query_vec, body.query)
    except Exception as exc:  # noqa: BLE001
        logger.exception("쿼리 임베딩 실패")
        raise HTTPException(status_code=500, detail=f"쿼리 임베딩 실패: {exc}")

    dept_labels = _resolve_dept_scope(user)
    # 필터: file_kinds→source_type, path_prefix(부분일치), dept 스코핑.
    # mtime은 Qdrant payload에 없어 매핑 불가(미결, 아래 후처리에서도 무시).
    qfilter = build_qdrant_filter(
        file_kinds=list(body.file_kinds) if body.file_kinds else None,
        path_prefix=body.path_prefix or None,
        dept_labels=dept_labels,
    )

    over_limit = body.limit * OVERFETCH_MULTIPLIER
    base_terms = tokenize_query(body.query)
    # 한글 토큰은 로마자(RR)도 키워드로 추가 — 문서에 영문 표기된 고객사명 등을
    # 한글 검색으로도 잡기 위함(예: "후이다" → "huida"). 키워드 arm은 OR 가산이라
    # 추가 토큰이 매칭되면 그 문서가 상위로 올라온다.
    romanized = [romanize_hangul(t) for t in base_terms if has_hangul(t)]
    terms = base_terms + [r for r in romanized if r and r not in base_terms]
    # 키워드 '고신뢰' 인정 최소 매칭 수 — 질의어 수와 결합(단일어 질의는 1).
    kw_min_match = min(KW_STRONG_MIN_MATCH, max(1, len(base_terms)))

    try:
        order_v, by_v = await asyncio.to_thread(vector_arm, query_vec, qfilter, over_limit)
        order_k, by_k = await asyncio.to_thread(keyword_arm, terms, qfilter, over_limit)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Qdrant 검색 실패")
        raise HTTPException(status_code=502, detail=f"Qdrant 검색 실패: {exc}")

    # 두 순위를 RRF로 결합(키=doc_id). 양쪽에 모두 등장한 문서가 상위로.
    rrf_scores = reciprocal_rank_fusion([order_v, order_k], k=RRF_K)
    ranked = sorted(rrf_scores, key=lambda d: rrf_scores[d], reverse=True)

    # 정직한 점수 + 관련도 게이트:
    #  - 키워드 매칭(쿼리어를 실제로 포함) → 높은 신뢰.
    #  - 벡터-only → raw cosine 그대로 노출(1.0 강제 정규화 안 함). 고유명사 등
    #    아무것도 안 맞을 때 벡터가 0.6대 노이즈를 반환하므로, 임계값 미만은 제외해
    #    "없으면 없다"가 되게 한다(nas_min_relevance, 튜닝 가능).
    min_rel = settings.nas_min_relevance
    hits: list[NasSearchHit] = []
    for doc_id in ranked:
        pl_k = by_k.get(doc_id)
        pl_v = by_v.get(doc_id)
        pl = pl_k or pl_v
        if pl is None:
            continue
        path = pl.get("path") or ""
        if body.path_prefix and body.path_prefix not in path:
            continue
        vec_score = (pl_v or {}).get("_score")
        # 키워드 '강매칭'만 0.85 고신뢰(게이트 면제). 흔한 토큰 1개만 걸린
        # 약매칭은 벡터 관련도 게이트로 강등해 노이즈 우회를 막는다.
        strong_kw = pl_k is not None and _keyword_is_strong(pl_k, kw_min_match)
        if strong_kw:
            confidence = max(0.85, float(vec_score or 0.0))  # 직접 포함 → 높게
        else:
            if vec_score is None or float(vec_score) < min_rel:
                continue  # 벡터-only(또는 키워드 약매칭) 노이즈 제외
            confidence = float(vec_score)
        source_type = pl.get("source_type")
        hits.append(
            NasSearchHit(
                id=_doc_id_to_uuid(doc_id),
                path=path,
                name=os.path.basename(path) if path else None,
                file_type=pl.get("modality") or "document",
                mime_type=_SOURCE_TYPE_TO_MIME.get(source_type or ""),
                size=None,
                mtime=None,
                dept=pl.get("dept"),
                score=round(min(1.0, confidence), 4),
                snippet=_build_snippet(pl.get("text") or ""),
            )
        )
        if len(hits) >= body.limit:
            break

    return NasSearchResponse(results=hits)


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


# Qdrant 검색결과는 nas_files에 없으므로 경로 기반 다운로드를 별도 제공.
_DOWNLOAD_ROOTS = ("/mnt/nas", "/mnt/nas-rnd", "/mnt/nas-rw")


@router.get("/files/download")
async def download_file_by_path(
    path: str,
    _user: User = Depends(get_current_user),
) -> FileResponse:
    """경로 기반 원본 다운로드(전 직원). 허용 루트(/mnt/nas, /mnt/nas-rnd) 검증."""
    if not any(_is_path_within_root(path, root) for root in _DOWNLOAD_ROOTS):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="허용되지 않은 경로")
    if not os.path.isfile(path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="원본 파일을 찾을 수 없습니다(NAS 마운트 확인)",
        )
    return FileResponse(path=path, filename=os.path.basename(path))
