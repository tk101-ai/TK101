"""문서 작업 공유 출처 레이어 — RAG / 사용자 업로드 / 둘다.

엔진(생성·채우기)은 출처가 어디서 왔는지 모른 채 `NasChunkHit[]` 만 받는다.
- rag:      nas_search.bridge.search_relevant_chunks (Qdrant)
- uploaded: 업로드 파일을 추출·청크해 같은 NasChunkHit 형태로 변환(통째 주입, 임베딩 불필요 → 토큰/검색 비용 0)
- both:     두 결과 합침

설계: docs/prd/PRD_DOCWORK_UNIFY_2026-06-22.md (PR-B 출처 레이어, PR-C extractor 이전).
"""
from __future__ import annotations

import logging

from app.schemas.docgen import SourceMode
from app.services.documents.extractor import extract_and_chunk, is_supported
from app.services.nas_search.bridge import NasChunkHit, search_relevant_chunks

logger = logging.getLogger(__name__)

# 업로드 파일 1건당 프롬프트에 넣을 최대 청크 수(과도한 토큰 방지).
UPLOAD_PER_FILE_CHUNK_LIMIT = 12


def uploaded_files_to_chunks(
    uploaded: list[tuple[bytes, str]],
) -> list[NasChunkHit]:
    """업로드 파일((bytes, filename)) 목록 → NasChunkHit 청크. 미지원/추출실패는 skip."""
    out: list[NasChunkHit] = []
    for data, filename in uploaded:
        if not is_supported(filename):
            logger.info("업로드 미지원 포맷 skip: %s", filename)
            continue
        doc = extract_and_chunk(data, filename)
        for i, content in enumerate(doc.chunks[:UPLOAD_PER_FILE_CHUNK_LIMIT]):
            out.append(
                NasChunkHit(
                    chunk_id="",
                    file_id="",
                    file_path=filename,
                    file_name=filename,
                    chunk_index=i,
                    content=content,
                    score=1.0,  # 사용자가 명시 지정한 자료 → 최고 신뢰.
                )
            )
    return out


async def collect_sources(
    *,
    query: str,
    mode: SourceMode,
    uploaded: list[tuple[bytes, str]],
    limit: int,
) -> list[NasChunkHit]:
    """출처 모드에 따라 RAG/업로드 청크를 모아 반환. 검색 실패는 생성을 막지 않는다."""
    chunks: list[NasChunkHit] = []
    if mode in ("rag", "both") and limit > 0:
        try:
            chunks += await search_relevant_chunks(query=query, limit=limit)
        except RuntimeError as exc:
            logger.warning("RAG 검색 실패 — 자료 없이 진행: %s", exc)
    if mode in ("uploaded", "both"):
        chunks += uploaded_files_to_chunks(uploaded)
    return chunks
