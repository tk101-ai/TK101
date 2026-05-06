"""T2 NAS 검색 브릿지 (FR-03).

라우터가 외부 HTTP 호출 없이 직접 같은 프로세스의 T2 검색 로직을 호출하도록 한다.
별도 RAG 인덱스 구축 금지 (PRD 6.2): nas_text_chunks 위에서 의미 검색만 사용.

흐름:
1. embed_query 로 쿼리 벡터화 (T2 embedder 재사용)
2. pgvector cosine 거리로 Top-N 청크 조회
3. nas_files + nas_text_chunks 조인 결과를 SourcePayload 후보로 변환
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nas_file import NasFile, NasTextChunk
from app.services.nas_search.embedder import embed_query

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


async def search_relevant_chunks(
    db: AsyncSession,
    *,
    query: str,
    limit: int = 20,
) -> list[NasChunkHit]:
    """쿼리 의미 검색 → 청크 단위 Top-N 결과.

    T2 routers/nas_search.py 의 search_text 와 달리, 본 함수는 청크 단위로 반환해
    매핑 단계에서 LLM에 직접 전달하기 좋은 형태다.
    """
    if not query.strip():
        return []

    try:
        query_vec = await asyncio.to_thread(embed_query, query)
    except Exception as exc:  # noqa: BLE001
        logger.exception("쿼리 임베딩 실패")
        raise RuntimeError(f"NAS 검색 쿼리 임베딩 실패: {exc}") from exc

    distance = NasTextChunk.embedding.cosine_distance(query_vec.tolist()).label("distance")
    stmt = (
        select(
            NasTextChunk.id,
            NasTextChunk.file_id,
            NasTextChunk.chunk_index,
            NasTextChunk.content,
            NasFile.path,
            NasFile.name,
            distance,
        )
        .join(NasFile, NasTextChunk.file_id == NasFile.id)
        .order_by(distance.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        NasChunkHit(
            chunk_id=str(row.id),
            file_id=str(row.file_id),
            file_path=row.path,
            file_name=row.name,
            chunk_index=int(row.chunk_index or 0),
            content=row.content or "",
            score=float(1.0 - row.distance),
        )
        for row in rows
    ]


async def fetch_chunks_by_ids(
    db: AsyncSession,
    chunk_ids: Iterable[str],
) -> list[NasChunkHit]:
    """이미 선택된 nas_text_chunks.id 목록으로 청크 조회 (검수 + 매핑 시점에 활용)."""
    ids = [cid for cid in chunk_ids if cid]
    if not ids:
        return []
    stmt = (
        select(
            NasTextChunk.id,
            NasTextChunk.file_id,
            NasTextChunk.chunk_index,
            NasTextChunk.content,
            NasFile.path,
            NasFile.name,
        )
        .join(NasFile, NasTextChunk.file_id == NasFile.id)
        .where(NasTextChunk.id.in_(ids))
    )
    result = await db.execute(stmt)
    rows = result.all()
    return [
        NasChunkHit(
            chunk_id=str(row.id),
            file_id=str(row.file_id),
            file_path=row.path,
            file_name=row.name,
            chunk_index=int(row.chunk_index or 0),
            content=row.content or "",
            score=0.0,  # 직접 fetch는 검색 점수가 없음
        )
        for row in rows
    ]


async def fetch_chunks_for_files(
    db: AsyncSession,
    file_ids: Iterable[str],
    *,
    per_file_limit: int = 5,
) -> list[NasChunkHit]:
    """선택된 nas_files.id 목록의 대표 청크들 (파일당 chunk_index 0부터 N개)."""
    ids = [fid for fid in file_ids if fid]
    if not ids:
        return []
    stmt = (
        select(
            NasTextChunk.id,
            NasTextChunk.file_id,
            NasTextChunk.chunk_index,
            NasTextChunk.content,
            NasFile.path,
            NasFile.name,
        )
        .join(NasFile, NasTextChunk.file_id == NasFile.id)
        .where(NasFile.id.in_(ids))
        .order_by(NasTextChunk.file_id, NasTextChunk.chunk_index)
    )
    result = await db.execute(stmt)
    rows = result.all()
    by_file: dict[str, list[NasChunkHit]] = {}
    for row in rows:
        fid = str(row.file_id)
        bucket = by_file.setdefault(fid, [])
        if len(bucket) >= per_file_limit:
            continue
        bucket.append(
            NasChunkHit(
                chunk_id=str(row.id),
                file_id=fid,
                file_path=row.path,
                file_name=row.name,
                chunk_index=int(row.chunk_index or 0),
                content=row.content or "",
                score=0.0,
            )
        )
    flat: list[NasChunkHit] = []
    for chunks in by_file.values():
        flat.extend(chunks)
    return flat
