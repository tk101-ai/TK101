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

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_admin, require_module
from app.models.nas_file import NasFile
from app.models.user import User
from app.modules.constants import Module
from app.schemas.nas_file import (
    NasCorpusDeptStat,
    NasCorpusStats,
    NasDeptStat,
    NasDeptsResponse,
    NasIndexProgress,
    NasSearchHit,
    NasSearchRequest,
    NasSearchResponse,
    NasStatus,
)
from app.services.nas_search import INDEX_PROGRESS, SUMMARY_PROGRESS
from app.services.nas_search.hybrid import (
    DEFAULT_RRF_K as RRF_K,
    reciprocal_rank_fusion,
    tokenize_query,
)
from app.services.nas_search.query_embedder import embed_query as embed_query_vec
from app.services.nas_search.reranker import rerank as rerank_passages
from app.services.nas_search.romanize import has_hangul, romanize_hangul
from app.services.nas_search.qdrant_search import (
    build_qdrant_filter,
    corpus_stats,
    keyword_arm,
    vector_arm,
)

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


@router.get("/corpus-stats", response_model=NasCorpusStats)
async def get_corpus_stats() -> NasCorpusStats:
    """현행 검색 코퍼스(Qdrant docs_text) 현황 — 총 청크 수 + 부서별 분포.

    구 in-app 인덱서(nas_files)가 아니라 실제 검색이 쓰는 Qdrant를 직접 조회한다.
    동기 Qdrant 클라이언트라 스레드로 오프로드. Qdrant 장애 시 502.
    """
    try:
        points, by_dept = await asyncio.to_thread(corpus_stats)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Qdrant 코퍼스 통계 조회 실패")
        raise HTTPException(status_code=502, detail=f"코퍼스 통계 조회 실패: {exc}")
    return NasCorpusStats(
        collection=settings.qdrant_collection_text,
        points_count=points,
        by_dept=[NasCorpusDeptStat(dept=d, count=c) for d, c in by_dept],
    )


@router.get("/depts", response_model=NasDeptsResponse)
async def list_depts() -> NasDeptsResponse:
    """검색 부서 필터 옵션 — 실제 검색 코퍼스(Qdrant docs_text)의 dept facet.

    구 nas_files 기반 폴더 목록(폐기)을 대체한다. corpus_stats()가 Qdrant dept
    facet으로 효율적으로 집계한 (dept, count) 리스트를 그대로 노출하므로 RND 등
    실제 검색 가능한 부서가 빠짐없이 나오고, #recycle 같은 비-부서 노이즈는 없다.
    동기 Qdrant 클라이언트라 스레드로 오프로드. Qdrant 장애 시 502.
    """
    try:
        _points, by_dept = await asyncio.to_thread(corpus_stats)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Qdrant 부서 facet 조회 실패")
        raise HTTPException(status_code=502, detail=f"부서 목록 조회 실패: {exc}")
    return NasDeptsResponse(
        depts=[NasDeptStat(dept=d, count=c) for d, c in by_dept],
    )


def _indexing_disabled() -> None:
    """인앱 인덱싱/backfill 비활성(deprecated/410).

    검색 코퍼스는 Qwen3(2560-dim)→Qdrant docs_text 단일 소스이며, 실제 적재는 외부
    파이프라인 /home/ubuntu/tk101-rag 가 담당한다. 과거 인앱 인덱싱은 레거시
    e5(1024-dim)→pgvector(nas_text_chunks)에 적재했으나 검색 미반영 dead data였고,
    해당 테이블·pgvector 확장은 032 마이그레이션에서 제거됨. 혼선·비용 방지를 위해 비활성.
    """
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail=(
            "인앱 인덱싱/backfill 은 제거되었습니다(레거시 e5/pgvector — 검색 미반영). "
            "임베딩 적재는 tk101-rag 파이프라인(Qwen3/Qdrant)을 사용하세요."
        ),
    )


@router.post(
    "/index/run",
    status_code=status.HTTP_410_GONE,
    dependencies=[Depends(require_admin)],
)
async def start_indexing() -> None:
    """[deprecated/410] 레거시 e5/pgvector 인덱싱 — 제거됨."""
    _indexing_disabled()


@router.post(
    "/index/backfill_filenames",
    status_code=status.HTTP_410_GONE,
    dependencies=[Depends(require_admin)],
)
async def start_filename_backfill() -> None:
    """[deprecated/410] 레거시 파일명 청크 backfill — 제거됨."""
    _indexing_disabled()


@router.post(
    "/index/backfill_summaries",
    status_code=status.HTTP_410_GONE,
    dependencies=[Depends(require_admin)],
)
async def start_summary_backfill() -> None:
    """[deprecated/410] 레거시 요약 청크 backfill — 제거됨."""
    _indexing_disabled()


@router.get("/index/status", response_model=NasIndexProgress)
async def get_index_status() -> NasIndexProgress:
    """인덱싱 진행률(legacy 호환). 인앱 인덱싱은 비활성이라 항상 idle."""
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


@router.get("/index/summary_status", response_model=NasIndexProgress)
async def get_summary_status() -> NasIndexProgress:
    """요약 backfill 진행률(legacy 호환). 비활성이라 항상 idle."""
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


def _effective_dept_labels(
    manual: list[str] | None,
    auto: list[str] | None,
) -> list[str] | None:
    """사용자 수동 부서 선택과 권한 자동 스코프를 안전하게 결합.

    - auto: _resolve_dept_scope (None=권한상 제한 없음/전체).
    - manual: 사용자가 UI에서 고른 부서들(None/빈 리스트=미선택=전체).

    규칙:
    - 수동 선택이 있으면 권한 스코프와 교집합(권한 밖 부서는 선택해도 무효).
      교집합이 비면 권한 스코프(auto)로 폴백 — 권한을 벗어나 전체로 풀리지 않게.
    - 수동 선택이 없으면 auto 그대로(권한 스코프 내 전체).
    """
    if manual:
        if auto is None:
            return list(manual)
        allowed = [d for d in manual if d in auto]
        return allowed or auto
    return auto


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

    dept_labels = _effective_dept_labels(body.depts, _resolve_dept_scope(user))
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
    # (hit, 청크 본문) 쌍 — 청크 본문은 리랭커 입력용(스니펫은 잘려 부적합).
    cands: list[tuple[NasSearchHit, str]] = []
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
        text = pl.get("text") or ""
        cands.append(
            (
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
                    snippet=_build_snippet(text),
                ),
                text,
            )
        )

    # 리랭킹: 상위 후보를 cross-encoder로 (쿼리,청크) 직접 채점해 재정렬한다.
    # ⚠️ 후보 풀은 confidence가 아니라 **RRF 순위(=cands 적재 순서)** 로 고른다.
    # confidence는 키워드 강매칭이 0.85로 뭉치고, 의미적으로 관련 높은(벡터 arm 상위)
    # 문서라도 키워드 강매칭이 아니면 cosine(~0.65)이라 0.85 그룹 아래로 밀린다 →
    # confidence로 후보를 고르면 정작 관련문서가 풀에서 빠져 재채점이 무의미해진다
    # (실측: confidence 풀이면 관련문서 탈락, RRF 풀이면 0.92로 1위). RRF는 벡터+
    # 키워드 순위를 합쳐 관련문서를 상위에 두므로 후보 선정에 더 안전하다.
    if settings.nas_rerank_enabled and len(cands) > 1:
        top = cands[: settings.nas_rerank_top_n]  # RRF 순서 상위 N
        try:
            scores = await asyncio.to_thread(
                rerank_passages, body.query, [t for _, t in top]
            )
            rescored = [
                hit.model_copy(update={"score": round(float(s), 4)})
                for (hit, _), s in zip(top, scores)
            ]
            rescored.sort(key=lambda h: h.score, reverse=True)
            return NasSearchResponse(results=rescored[: body.limit])
        except Exception:  # noqa: BLE001
            logger.exception("리랭킹 실패 — 1차 점수순으로 폴백")

    # 리랭커 off/실패 시: 표시 점수(confidence) 내림차순으로 노출.
    cands.sort(key=lambda c: c[0].score, reverse=True)
    return NasSearchResponse(results=[hit for hit, _ in cands[: body.limit]])


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
