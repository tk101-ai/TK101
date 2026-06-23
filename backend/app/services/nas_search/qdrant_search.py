"""Qdrant 기반 검색 arm들 (NAS 검색 v2 — 단일 소스).

벡터 arm + 키워드 arm 둘 다 Qdrant docs_text를 조회한다. 결합 키는 path가
아니라 **doc_id**(Qdrant payload 전건 보유)다. 두 arm 모두 doc_id 단위로
dedup해 (doc_id 순위 리스트, doc_id→대표 payload) 를 돌려준다. 라우터가 이를
RRF(hybrid.reciprocal_rank_fusion)로 doc_id 키로 결합한다.

인덱싱 파이프라인 규약(/home/ubuntu/tk101-rag/config.py, retriever.py) 복제:
- 컬렉션 docs_text, 2560-dim, cosine.
- payload: modality, doc_id, file_hash, dept, brand, year, is_archived,
  confidential, source_type, path, page, chunk_index, n_chunks, text.

키워드 arm 설계 메모:
- Qdrant payload `text`에는 풀텍스트 인덱스(MatchText)가 없다(payload_schema에
  text 부재 — 인덱싱 파이프라인 소관이라 백엔드에서 컬렉션을 변형하지 않는다).
  따라서 후보를 scroll로 넉넉히 가져와 토큰 substring AND-매칭으로 후처리한다.
  품번/고유명사 같은 정확 토큰을 잡는 것이 목적. 토큰이 여러 개면 AND(모두
  포함)할수록 상위, 부족하면 매칭 토큰 수 내림차순.
- text에 풀텍스트 인덱스가 생기면 vector_arm처럼 query_filter MatchText로
  전환 가능(통합 단계 과제, 함수 시그니처는 불변 유지).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client import models as qm

from app.config import settings

logger = logging.getLogger(__name__)

_client: QdrantClient | None = None
_client_lock = threading.Lock()


def get_client() -> QdrantClient:
    """QdrantClient 싱글톤. 멀티스레드 안전."""
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is not None:
            return _client
        logger.info("QdrantClient 생성: %s", settings.qdrant_url)
        _client = QdrantClient(url=settings.qdrant_url, timeout=30)
        return _client


# ── 코퍼스 통계 (대시보드용) ──────────────────────────────────────────────────

def corpus_stats() -> tuple[int, list[tuple[str, int]]]:
    """현행 검색 코퍼스(docs_text)의 총 청크 수 + 부서별 분포.

    적재는 외부 파이프라인(tk101-rag)이 하므로 여기서는 읽기만 한다(컬렉션
    변형 없음). facet 미지원/실패 시 by_dept는 빈 리스트로 폴백한다.
    동기 클라이언트이므로 호출부(라우터)에서 스레드로 오프로드할 것.
    """
    client = get_client()
    info = client.get_collection(settings.qdrant_collection_text)
    points = int(info.points_count or 0)
    by_dept: list[tuple[str, int]] = []
    try:
        res = client.facet(
            collection_name=settings.qdrant_collection_text,
            key="dept",
            limit=50,
        )
        by_dept = sorted(
            ((str(h.value), int(h.count)) for h in res.hits),
            key=lambda x: -x[1],
        )
    except Exception:  # noqa: BLE001
        logger.exception("Qdrant dept facet 실패 — by_dept 생략")
    return points, by_dept


# ── 필터 빌더 ────────────────────────────────────────────────────────────────

# file_kinds(스키마) → Qdrant payload source_type(인덱싱 파이프라인 원본 형식).
# hwp는 HWP5/HWPX 모두 source_type "hwp"로 적재된다고 가정(인덱서 규약).
FILE_KIND_SOURCE_TYPES: dict[str, list[str]] = {
    "pdf": ["pdf"],
    "word": ["docx"],
    "ppt": ["pptx"],
    "hwp": ["hwp", "hwpx"],
    "excel": ["xlsx"],
}


def _flatten_source_types(kinds: list[str]) -> list[str]:
    out: list[str] = []
    for kind in kinds:
        out.extend(FILE_KIND_SOURCE_TYPES.get(kind, []))
    return out


def build_qdrant_filter(
    *,
    file_kinds: list[str] | None = None,
    path_prefix: str | None = None,
    mtime_from: datetime | None = None,  # noqa: ARG001 (Qdrant payload에 mtime 없음)
    mtime_to: datetime | None = None,  # noqa: ARG001
    dept_labels: list[str] | None = None,
) -> qm.Filter | None:
    """검색 필터를 Qdrant Filter로 매핑.

    매핑 가능 범위:
    - file_kinds → payload source_type (MatchAny).
      ※ source_type에 payload 인덱스가 없으면 Qdrant가 거부할 수 있다 → 라우터에서
        post-filter 폴백을 둔다(아래 source_type_post_filter 참고).
    - path_prefix → payload path (MatchText로 부분일치; 정확한 prefix는 후처리에서 보정).
    - dept_labels → payload dept (MatchAny) — 부서 스코핑.
    - mtime_from/mtime_to → Qdrant payload에 mtime이 없어 매핑 불가(None 무시).
      필요 시 인덱싱 파이프라인에 mtime payload 추가가 선행돼야 한다(미결).
    """
    must: list[qm.Condition] = []
    if dept_labels:
        must.append(qm.FieldCondition(key="dept", match=qm.MatchAny(any=list(dept_labels))))
    if file_kinds:
        stypes = _flatten_source_types(list(file_kinds))
        if stypes:
            must.append(
                qm.FieldCondition(key="source_type", match=qm.MatchAny(any=stypes))
            )
    if path_prefix:
        # path는 payload 인덱스가 없을 수 있어 MatchText(부분일치)로 시도하고,
        # 정확한 prefix 검증은 라우터 후처리(startswith)로 보정한다.
        must.append(qm.FieldCondition(key="path", match=qm.MatchText(text=path_prefix)))
    return qm.Filter(must=must) if must else None


def _payload_of(point: Any) -> dict:
    return dict(point.payload or {})


def _dedup_by_doc_id(
    points: list[Any],
) -> tuple[list[str], dict[str, dict]]:
    """best-first points → (doc_id 순위 리스트, doc_id→대표 payload).

    같은 doc_id의 첫 등장(=상위 청크)만 대표로 남긴다.
    doc_id가 없으면 path를 폴백 키로 사용(레거시 안전).
    """
    order: list[str] = []
    by_doc: dict[str, dict] = {}
    for p in points:
        pl = _payload_of(p)
        key = pl.get("doc_id") or pl.get("path")
        if not key or key in by_doc:
            continue
        # 점수 보존(벡터 arm 디버깅/표시용).
        pl["_score"] = getattr(p, "score", None)
        by_doc[key] = pl
        order.append(key)
    return order, by_doc


# ── 벡터 arm ─────────────────────────────────────────────────────────────────

def vector_arm(
    query_vec: list[float],
    qfilter: qm.Filter | None,
    limit: int,
) -> tuple[list[str], dict[str, dict]]:
    """의미검색 arm — Qdrant cosine 유사도 top-N → doc_id dedup.

    over-fetch는 라우터가 limit에 배수를 곱해 넘긴다(파일 그룹핑 손실 보정).
    """
    res = get_client().query_points(
        collection_name=settings.qdrant_collection_text,
        query=query_vec,
        query_filter=qfilter,
        limit=limit,
        with_payload=True,
    ).points
    return _dedup_by_doc_id(res)


# ── 키워드 arm ───────────────────────────────────────────────────────────────

def _scroll_candidates(
    qfilter: qm.Filter | None,
    scan_limit: int,
) -> list[Any]:
    """필터에 맞는 후보 payload를 scroll로 수집(text substring 후처리용)."""
    out: list[Any] = []
    next_page = None
    remaining = scan_limit
    client = get_client()
    while remaining > 0:
        batch, next_page = client.scroll(
            collection_name=settings.qdrant_collection_text,
            scroll_filter=qfilter,
            limit=min(1000, remaining),
            offset=next_page,
            with_payload=True,
            with_vectors=False,
        )
        if not batch:
            break
        out.extend(batch)
        remaining -= len(batch)
        if next_page is None:
            break
    return out


def _fulltext_token_filter(
    tokens: list[str], qfilter: qm.Filter | None
) -> qm.Filter | None:
    """토큰을 `text`/`path` 풀텍스트(MatchText)로 거르는 필터를 만든다.

    토큰 중 **하나라도** text 또는 path 에 매칭되면 후보(should=OR). 기존 qfilter
    (부서 스코핑 등)가 있으면 AND로 중첩한다. word 토크나이저 min_token_len=2 라
    1글자 토큰은 인덱스에 없어 필터에 기여하지 못하므로 제외(있어도 무해하나 노이즈).
    매칭수 기반 랭킹은 아래 파이썬 점수화가 그대로 담당(필터는 후보 추림만).
    """
    should: list[Any] = []
    for t in tokens:
        if len(t) < 2:
            continue
        should.append(qm.FieldCondition(key="text", match=qm.MatchText(text=t)))
        should.append(qm.FieldCondition(key="path", match=qm.MatchText(text=t)))
    if not should:
        return qfilter  # 전부 1글자 → 풀텍스트 필터 불가, 기존 필터만
    token_filter = qm.Filter(should=should)
    if qfilter is None:
        return token_filter
    return qm.Filter(must=[qfilter, token_filter])


def keyword_arm(
    tokens: list[str],
    qfilter: qm.Filter | None,
    limit: int,
    *,
    scan_limit: int | None = None,
) -> tuple[list[str], dict[str, dict]]:
    """정확검색 arm — payload `text`/`path`에 대한 토큰 매칭.

    풀텍스트 인덱스(MatchText)가 있으면 토큰 포함 문서만 **전체 코퍼스에서** 추린 뒤
    scan_limit 안에서 점수화한다(과거: 임의 prefix 4000 scroll = 코퍼스 0.6%만 봄).
    각 토큰이 text 또는 path(파일명 포함)에 부분일치하면 +1. 매칭 토큰 수가 많을수록
    상위. doc_id 단위 dedup. tokens가 비면 빈 결과(벡터 arm만으로 동작).
    """
    if not tokens:
        return [], {}

    scan_limit = scan_limit or settings.nas_keyword_scan_limit
    scroll_filter = (
        _fulltext_token_filter(tokens, qfilter)
        if settings.nas_keyword_fulltext
        else qfilter
    )
    candidates = _scroll_candidates(scroll_filter, scan_limit)
    lowered = [t.lower() for t in tokens]

    scored: list[tuple[int, list[str], dict, str]] = []
    seen: set[str] = set()
    for p in candidates:
        pl = _payload_of(p)
        key = pl.get("doc_id") or pl.get("path")
        if not key:
            continue
        haystack = f"{pl.get('text', '')}\n{pl.get('path', '')}".lower()
        matched = [t for t in lowered if t in haystack]
        if not matched:
            continue
        # 같은 doc_id는 첫 등장(=scroll 상위 청크)만 대표로.
        if key in seen:
            continue
        seen.add(key)
        scored.append((len(matched), matched, pl, key))

    # 매칭 토큰 수 내림차순. 동점은 안정 정렬(scroll 순서 유지).
    scored.sort(key=lambda x: x[0], reverse=True)
    scored = scored[:limit]

    order: list[str] = []
    by_doc: dict[str, dict] = {}
    for match_count, matched, pl, key in scored:
        pl["_match_count"] = match_count
        # 어떤 토큰이 걸렸는지 보존 → 라우터가 약매칭(흔한 토큰 1개)을
        # 0.85 고신뢰에서 제외하는 데 사용(노이즈 게이트 우회 방지).
        pl["_matched_tokens"] = matched
        by_doc[key] = pl
        order.append(key)
    return order, by_doc
