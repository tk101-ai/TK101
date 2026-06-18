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
from dataclasses import dataclass
from typing import Iterable

from qdrant_client import models as qm

from app.config import settings
from app.services.nas_search.qdrant_search import get_client
from app.services.nas_search.query_embedder import embed_query

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


async def search_relevant_chunks(
    db=None,  # noqa: ANN001 (호환 유지용; Qdrant 경로에선 미사용)
    *,
    query: str,
    limit: int = 20,
    dept_labels: list[str] | None = None,
) -> list[NasChunkHit]:
    """쿼리 의미 검색 → 청크 단위 Top-N 결과(Qdrant cosine).

    nas_search.search_text 와 달리 청크 단위로 반환해 매핑 단계에서 LLM에 직접
    전달하기 좋은 형태다. dept_labels 를 주면 해당 부서로 스코핑한다.
    """
    if not query.strip():
        return []

    try:
        query_vec = await asyncio.to_thread(embed_query, query)
    except Exception as exc:  # noqa: BLE001
        logger.exception("쿼리 임베딩 실패")
        raise RuntimeError(f"NAS 검색 쿼리 임베딩 실패: {exc}") from exc

    qfilter = None
    if dept_labels:
        qfilter = qm.Filter(
            must=[qm.FieldCondition(key="dept", match=qm.MatchAny(any=list(dept_labels)))]
        )

    try:
        points = await asyncio.to_thread(
            lambda: get_client()
            .query_points(
                collection_name=settings.qdrant_collection_text,
                query=query_vec,
                query_filter=qfilter,
                limit=limit,
                with_payload=True,
            )
            .points
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Qdrant 검색 실패")
        raise RuntimeError(f"NAS 검색 실패: {exc}") from exc

    return [_hit_from_point(p, score=float(getattr(p, "score", 0.0) or 0.0)) for p in points]


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

    by_file: dict[str, list[NasChunkHit]] = {}
    for r in records:
        hit = _hit_from_point(r, score=0.0)
        bucket = by_file.setdefault(hit.file_id, [])
        bucket.append(hit)
    flat: list[NasChunkHit] = []
    for chunks in by_file.values():
        chunks.sort(key=lambda h: h.chunk_index)
        flat.extend(chunks[:per_file_limit])
    return flat


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

    by_path: dict[str, list[NasChunkHit]] = {}
    for r in records:
        hit = _hit_from_point(r, score=0.0)
        by_path.setdefault(hit.file_path, []).append(hit)
    flat: list[NasChunkHit] = []
    for chunks in by_path.values():
        chunks.sort(key=lambda h: h.chunk_index)
        flat.extend(chunks[:per_file_limit])
    return flat
