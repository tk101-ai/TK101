"""T2 NAS 검색 브릿지 (FR-03).

라우터가 외부 HTTP 없이 같은 프로세스에서 NAS 의미검색을 호출하도록 한다.

데이터 소스 = **Qdrant docs_text 단일 소스**(T2 v2). 인덱싱 파이프라인
(/home/ubuntu/tk101-rag)이 문서를 raw 임베딩해 적재하고, 쿼리는 Qwen3-Embedding
(query_embedder, instruction 프리픽스)으로 임베딩해 cosine 검색한다.

※ 과거에는 레거시 pgvector(nas_text_chunks, e5 임베딩)를 조회했으나, 검색엔진이
  Qdrant/Qwen3로 교체되면서 그 인덱스는 마이그레이션 이전 스냅샷(구모델)만 담고
  있어 신규 코퍼스(마케팅·신사업·RND·COMPANY 등)를 전혀 보지 못했다. 이제
  nas_search 와 동일한 Qdrant 소스를 써서 문서작성도 전체 코퍼스를 활용한다.

청크 식별자(chunk_id) = Qdrant point id. file_id = payload doc_id(문서 단위 식별).
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, replace
from typing import Iterable

from qdrant_client import models as qm

from app.config import settings
from app.services.nas_search.qdrant_search import get_client
from app.services.nas_search.query_embedder import embed_queries, embed_query
from app.services.nas_search.reranker import rerank as _rerank_passages

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NasChunkHit:
    """검색 결과 청크 1건. 라우터가 form_data_sources 저장 + mapper.SourcePayload 변환에 사용."""

    chunk_id: str
    file_id: str
    file_path: str
    file_name: str | None
    chunk_index: int
    content: str
    score: float


def build_query_from_variables(
    variables: list[dict] | None,
    template_name: str | None = None,
    *,
    max_terms: int = 12,
) -> str:
    """양식 변수 라벨(+양식명)로 NAS 의미검색 쿼리를 자동 생성한다(B2 자동쿼리).

    사용자가 검색어를 직접 안 쳐도 "이 양식과 관련된 자료"를 찾도록, 변수 라벨을
    모아 한 줄 쿼리를 만든다. LLM 호출 없이 결정적(저비용)이다. 더 정교한
    변수별 병렬 검색은 후속 과제.
    """
    parts: list[str] = []
    seen: set[str] = set()
    if template_name and template_name.strip():
        parts.append(template_name.strip())
        seen.add(template_name.strip().lower())
    for v in variables or []:
        label = str((v.get("label") or v.get("key") or "")).strip()
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        parts.append(label)
        if len(parts) >= max_terms:
            break
    return " ".join(parts).strip()


def _dept_filter(dept_labels: list[str] | None):
    """부서 라벨 스코핑용 Qdrant 필터(없으면 None)."""
    if not dept_labels:
        return None
    return qm.Filter(
        must=[qm.FieldCondition(key="dept", match=qm.MatchAny(any=list(dept_labels)))]
    )


def _bucket_top_chunks(records, key_fn, per_file_limit: int) -> list[NasChunkHit]:
    """scroll 레코드를 key 별 버킷으로 모아 chunk_index 오름차순 상위 N개만 평탄화.

    fetch_chunks_for_files(doc_id 기준)·fetch_chunks_for_paths(path 기준) 공통 로직.
    """
    buckets: dict[str, list[NasChunkHit]] = {}
    for r in records:
        hit = _hit_from_point(r, score=0.0)
        buckets.setdefault(key_fn(hit), []).append(hit)
    flat: list[NasChunkHit] = []
    for chunks in buckets.values():
        chunks.sort(key=lambda h: h.chunk_index)
        flat.extend(chunks[:per_file_limit])
    return flat


def _hit_from_point(point, *, score: float) -> NasChunkHit:
    """Qdrant point(payload 포함) → NasChunkHit. 점수는 호출부가 전달."""
    pl = dict(getattr(point, "payload", None) or {})
    path = pl.get("path") or ""
    return NasChunkHit(
        chunk_id=str(point.id),
        file_id=str(pl.get("doc_id") or ""),
        file_path=path,
        file_name=os.path.basename(path) if path else None,
        chunk_index=int(pl.get("chunk_index") or 0),
        content=pl.get("text") or "",
        score=score,
    )


# bridge 리랭크 후보 풀 = limit * 배수 (상한). 리랭커는 CPU(~0.38s/passage)라
# 무한정 키우면 docgen/채팅 지연이 커진다. 상한으로 지연을 묶는다.
_BRIDGE_RERANK_MULTIPLIER = 3
_BRIDGE_RERANK_CAP = 30


def _boost_self_company(hits: list[NasChunkHit]) -> list[NasChunkHit]:
    """자체 회사문서(경로에 self-company 마커) 점수에 가산 부스트 후 재정렬.

    코퍼스에서 절대 소수인 자체 자료(회사소개서 등)가 비슷한 점수대의 고객사 문서에
    밀려 묻히지 않도록 작은 가산점을 준다(설정 ``nas_self_company_boost``). 비활성(0)
    이거나 마커 미설정이면 원본 순서 그대로 반환. 불변(replace)으로 새 리스트 생성.
    """
    boost = settings.nas_self_company_boost
    marker = settings.nas_self_company_path_marker
    if boost <= 0 or not marker:
        return hits
    boosted = [
        replace(h, score=h.score + boost) if marker in (h.file_path or "") else h
        for h in hits
    ]
    boosted.sort(key=lambda h: h.score, reverse=True)
    return boosted


def _rrf_merge(result_lists: list[list[NasChunkHit]], k: int) -> list[NasChunkHit]:
    """언어별 결과 리스트들을 RRF(Reciprocal Rank Fusion)로 병합.

    각 리스트의 순위(1부터)만 쓰므로 KO/ZH/EN 코사인 점수 스케일 차이(예 0.64 vs
    0.69)에 영향받지 않고 언어 균형이 맞는다. 같은 chunk 가 여러 언어 풀에 나오면
    가산돼(크로스링구얼 합의) 상위로 올라온다. fused 값을 hit.score 로 실어
    downstream(cap_per_file·source_paths)이 그대로 순서를 쓰게 한다.
    """
    fused: dict[str, float] = {}
    rep: dict[str, NasChunkHit] = {}
    for hits in result_lists:
        for rank, h in enumerate(hits, start=1):
            fused[h.chunk_id] = fused.get(h.chunk_id, 0.0) + 1.0 / (k + rank)
            rep.setdefault(h.chunk_id, h)
    merged = [replace(rep[cid], score=score) for cid, score in fused.items()]
    merged.sort(key=lambda h: h.score, reverse=True)
    return merged


def _boost_self_company_rrf(hits: list[NasChunkHit], k: int) -> list[NasChunkHit]:
    """RRF 공간에서의 자체 회사문서 부스트. cosine 공간의 ``_boost_self_company`` 와
    같은 의도지만, RRF 점수는 스케일이 작아(≈1/k) 고정 가산(0.06)이 과하다. 대신
    '최상위 1표'에 해당하는 ``1/(k+1)`` 만큼 가산해 비슷한 순위대에서 자체문서를
    앞세운다. 설정 부스트가 0이거나 마커 미설정이면 원본 순서 그대로."""
    if settings.nas_self_company_boost <= 0 or not settings.nas_self_company_path_marker:
        return hits
    marker = settings.nas_self_company_path_marker
    bonus = 1.0 / (k + 1)
    boosted = [
        replace(h, score=h.score + bonus) if marker in (h.file_path or "") else h
        for h in hits
    ]
    boosted.sort(key=lambda h: h.score, reverse=True)
    return boosted


async def search_relevant_chunks_multilingual(
    db=None,  # noqa: ANN001 (호환 유지용)
    *,
    queries: list[str],
    limit: int = 20,
    dept_labels: list[str] | None = None,
) -> list[NasChunkHit]:
    """다국어 쿼리 변형들을 각각 검색해 RRF 로 병합(크로스링구얼 커버리지).

    ``queries`` = [ko, zh, en] 처럼 언어별 검색어. Qwen3 임베딩의 same-language
    편향으로 한국어 단일쿼리는 중문·영문 문서를 후보 풀에 아예 못 담는다(리랭커로도
    복구 불가 — 풀에 없으니까). 각 변형이 자기 언어 풀을 검색하게 하고 RRF(순위기반)
    로 병합해 언어 균형을 맞춘다. 지연 민감 경로(채팅)용이라 리랭크는 쓰지 않는다.
    변형이 1개뿐이면 기존 raw-cosine 경로로 위임한다.
    """
    variants = [q.strip() for q in (queries or []) if q and q.strip()]
    if not variants:
        return []
    if len(variants) == 1:
        return await search_relevant_chunks(
            query=variants[0], limit=limit, dept_labels=dept_labels, rerank=False
        )

    try:
        vecs = await asyncio.to_thread(embed_queries, variants)
    except Exception as exc:  # noqa: BLE001
        logger.exception("다국어 쿼리 임베딩 실패")
        raise RuntimeError(f"다국어 NAS 검색 임베딩 실패: {exc}") from exc

    qfilter = _dept_filter(dept_labels)
    # 언어별 풀을 넉넉히(limit*2, 상한) 뽑아 RRF 병합 여지를 준다.
    pool = min(limit * 2, _BRIDGE_RERANK_CAP)

    def _one(vec):
        return (
            get_client()
            .query_points(
                collection_name=settings.qdrant_collection_text,
                query=vec,
                query_filter=qfilter,
                limit=pool,
                with_payload=True,
            )
            .points
        )

    results = await asyncio.gather(
        *[asyncio.to_thread(_one, v) for v in vecs], return_exceptions=True
    )
    result_lists: list[list[NasChunkHit]] = []
    for res in results:
        if isinstance(res, Exception):
            logger.warning("다국어 검색 일부 실패(건너뜀): %s", res)
            continue
        result_lists.append(
            [
                _hit_from_point(p, score=float(getattr(p, "score", 0.0) or 0.0))
                for p in res
            ]
        )
    if not result_lists:
        return []

    k = settings.nas_multilingual_rrf_k
    merged = _rrf_merge(result_lists, k)
    return _boost_self_company_rrf(merged, k)[:limit]


async def search_relevant_chunks(
    db=None,  # noqa: ANN001 (호환 유지용; Qdrant 경로에선 미사용)
    *,
    query: str,
    limit: int = 20,
    dept_labels: list[str] | None = None,
    rerank: bool = True,
) -> list[NasChunkHit]:
    """쿼리 의미 검색 → 청크 단위 Top-N 결과(Qdrant cosine + bge 리랭크/게이트).

    nas_search.search_text 와 달리 청크 단위로 반환해 매핑/문서생성 단계에서 LLM에
    직접 전달하기 좋은 형태다. dept_labels 를 주면 해당 부서로 스코핑한다.

    검색 라우터와 동일하게, raw cosine 상위만 그대로 주면 0.3~0.5대 노이즈 청크가
    LLM 근거로 주입되므로(문서 품질 저하), 후보를 넉넉히 가져와 **bge 리랭커**로
    재채점하고 **nas_rerank_min_score** 게이트로 노이즈를 떨군다. rerank=False 면
    과거처럼 raw cosine Top-N (지연 민감 경로용).
    """
    if not query.strip():
        return []

    try:
        query_vec = await asyncio.to_thread(embed_query, query)
    except Exception as exc:  # noqa: BLE001
        logger.exception("쿼리 임베딩 실패")
        raise RuntimeError(f"NAS 검색 쿼리 임베딩 실패: {exc}") from exc

    qfilter = _dept_filter(dept_labels)
    use_rerank = rerank and settings.nas_rerank_enabled
    boost_on = settings.nas_self_company_boost > 0 and bool(
        settings.nas_self_company_path_marker
    )
    if use_rerank:
        fetch_n = min(limit * _BRIDGE_RERANK_MULTIPLIER, _BRIDGE_RERANK_CAP)
    elif boost_on:
        # 부스트가 켜진 비리랭크 경로: 자체문서가 top-N 바로 밖에 있어도 부스트로
        # 끌어올릴 수 있게 후보 풀을 약간 넓게 가져온 뒤 재정렬·절단한다.
        fetch_n = min(limit * 2, _BRIDGE_RERANK_CAP)
    else:
        fetch_n = limit

    try:
        points = await asyncio.to_thread(
            lambda: get_client()
            .query_points(
                collection_name=settings.qdrant_collection_text,
                query=query_vec,
                query_filter=qfilter,
                limit=fetch_n,
                with_payload=True,
            )
            .points
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Qdrant 검색 실패")
        raise RuntimeError(f"NAS 검색 실패: {exc}") from exc

    hits = [
        _hit_from_point(p, score=float(getattr(p, "score", 0.0) or 0.0)) for p in points
    ]
    if not use_rerank or len(hits) <= 1:
        return _boost_self_company(hits)[:limit]

    # bge 리랭커로 (쿼리,청크) 직접 재채점 → 게이트(노이즈 ~0.001 / 관련 0.6~0.98).
    try:
        scores = await asyncio.to_thread(
            _rerank_passages,
            query,
            [(h.content or "")[: settings.nas_rerank_max_length] for h in hits],
        )
    except Exception:  # noqa: BLE001 — 리랭크 실패는 검색을 막지 않는다(raw 폴백).
        logger.exception("bridge 리랭크 실패 — raw cosine 폴백")
        return hits[:limit]

    rescored = [replace(h, score=float(s)) for h, s in zip(hits, scores)]
    rescored.sort(key=lambda h: h.score, reverse=True)
    gated = [h for h in rescored if h.score >= settings.nas_rerank_min_score]
    # 부스트는 게이트 **후** 적용 — 관련 없는 자체문서(게이트 미통과)는 그대로
    # 떨구고, 관련 있는 자체문서만 비슷한 점수대에서 우선시한다.
    return _boost_self_company(gated)[:limit]


def _variable_queries(variables, template_name, max_vars):
    """변수 라벨(+양식명)로 변수별 검색 쿼리 목록 생성(중복 라벨 제거)."""
    out: list[str] = []
    seen: set[str] = set()
    prefix = f"{template_name} " if template_name else ""
    for v in variables or []:
        label = str((v.get("label") or v.get("key") or "")).strip()
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        out.append(f"{prefix}{label}".strip())
        if len(out) >= max_vars:
            break
    return out


async def search_per_variable(
    db=None,  # noqa: ANN001 (호환 유지용)
    *,
    variables: list[dict],
    template_name: str | None = None,
    per_var_limit: int = 3,
    max_vars: int = 12,
    dept_labels: list[str] | None = None,
) -> list[NasChunkHit]:
    """양식 변수별로 NAS 의미검색을 **병렬**로 돌려 자료 커버리지를 높인다(B 변수별 검색).

    단일 통합쿼리보다 각 변수(캠페인명/기간/예산 등)에 맞는 청크를 더 잘 잡는다.
    쿼리는 한 번에 배치 임베딩(embed_queries)하고, Qdrant 조회는 동시 실행한 뒤
    point id 기준 중복 제거(최고 점수 보존).
    """
    queries = _variable_queries(variables, template_name, max_vars)
    if not queries:
        return []
    try:
        vecs = await asyncio.to_thread(embed_queries, queries)
    except Exception as exc:  # noqa: BLE001
        logger.exception("변수별 쿼리 임베딩 실패")
        raise RuntimeError(f"변수별 NAS 검색 임베딩 실패: {exc}") from exc

    qfilter = _dept_filter(dept_labels)

    def _one(vec):
        return (
            get_client()
            .query_points(
                collection_name=settings.qdrant_collection_text,
                query=vec,
                query_filter=qfilter,
                limit=per_var_limit,
                with_payload=True,
            )
            .points
        )

    try:
        results = await asyncio.gather(
            *[asyncio.to_thread(_one, v) for v in vecs], return_exceptions=True
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("변수별 Qdrant 검색 실패")
        raise RuntimeError(f"변수별 NAS 검색 실패: {exc}") from exc

    best: dict[str, NasChunkHit] = {}
    for res in results:
        if isinstance(res, Exception):
            logger.warning("변수별 검색 일부 실패(건너뜀): %s", res)
            continue
        for p in res:
            hit = _hit_from_point(p, score=float(getattr(p, "score", 0.0) or 0.0))
            cur = best.get(hit.chunk_id)
            if cur is None or hit.score > cur.score:
                best[hit.chunk_id] = hit
    return sorted(best.values(), key=lambda h: h.score, reverse=True)


async def fetch_chunks_by_ids(
    db=None,  # noqa: ANN001 (호환 유지용)
    chunk_ids: Iterable[str] = (),
) -> list[NasChunkHit]:
    """이미 선택된 Qdrant point id 목록으로 청크 재조회 (검수 + 매핑 시점)."""
    ids = [cid for cid in chunk_ids if cid]
    if not ids:
        return []
    try:
        records = await asyncio.to_thread(
            lambda: get_client().retrieve(
                collection_name=settings.qdrant_collection_text,
                ids=ids,
                with_payload=True,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Qdrant 청크 조회 실패")
        raise RuntimeError(f"NAS 청크 조회 실패: {exc}") from exc
    # 직접 fetch는 검색 점수가 없음(0.0).
    return [_hit_from_point(r, score=0.0) for r in records]


async def fetch_chunks_for_files(
    db=None,  # noqa: ANN001 (호환 유지용)
    file_ids: Iterable[str] = (),
    *,
    per_file_limit: int = 5,
) -> list[NasChunkHit]:
    """선택된 문서(doc_id) 목록의 대표 청크들 (문서당 chunk_index 낮은 순 N개)."""
    ids = [fid for fid in file_ids if fid]
    if not ids:
        return []
    try:
        records, _ = await asyncio.to_thread(
            lambda: get_client().scroll(
                collection_name=settings.qdrant_collection_text,
                scroll_filter=qm.Filter(
                    must=[qm.FieldCondition(key="doc_id", match=qm.MatchAny(any=ids))]
                ),
                # 문서당 per_file_limit 를 넉넉히 커버하도록 스크롤 상한을 둔다.
                limit=max(len(ids) * per_file_limit * 4, 256),
                with_payload=True,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Qdrant 파일 청크 조회 실패")
        raise RuntimeError(f"NAS 파일 청크 조회 실패: {exc}") from exc

    return _bucket_top_chunks(records, lambda h: h.file_id, per_file_limit)


async def fetch_chunks_for_paths(
    db=None,  # noqa: ANN001 (호환 유지용)
    paths: Iterable[str] = (),
    *,
    per_file_limit: int = 5,
) -> list[NasChunkHit]:
    """선택된 파일 경로(payload path) 목록의 대표 청크들. NAS 검색결과에서 doc_id 대신
    안정적인 path 로 '파일 단위' 선택을 처리(검색 hit.id 는 doc_id→UUID 인코딩이라
    Qdrant 조회 키로 못 씀)."""
    keys = [p for p in paths if p]
    if not keys:
        return []
    try:
        records, _ = await asyncio.to_thread(
            lambda: get_client().scroll(
                collection_name=settings.qdrant_collection_text,
                scroll_filter=qm.Filter(
                    must=[qm.FieldCondition(key="path", match=qm.MatchAny(any=keys))]
                ),
                limit=max(len(keys) * per_file_limit * 4, 256),
                with_payload=True,
            )
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Qdrant 경로 청크 조회 실패")
        raise RuntimeError(f"NAS 경로 청크 조회 실패: {exc}") from exc

    return _bucket_top_chunks(records, lambda h: h.file_path, per_file_limit)
