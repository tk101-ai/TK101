"""Playground NAS RAG 헬퍼 (2026-06-18).

채팅 답변 전에 회사 NAS 문서(Qdrant 코퍼스, 68만+ 청크)에서 관련 청크를 검색해
LLM system 컨텍스트로 주입한다. 검색 인프라는 문서작성 모듈과 동일한
``nas_search.bridge.search_relevant_chunks`` 를 **재사용**(읽기/import 만)한다.

설계 원칙(MVP):
- 임베딩/검색 실패는 채팅을 막지 않는다 — 경고 로깅 후 빈 결과로 graceful fallback.
- 0건이면 컨텍스트 주입 없이 일반 채팅으로 진행.
- 사용한 출처 경로는 프론트가 표시할 수 있게 별도로 반환한다.
"""
from __future__ import annotations

import asyncio
import logging

from app.services.nas_search.bridge import (
    NasChunkHit,
    search_relevant_chunks,
)

logger = logging.getLogger(__name__)

# RAG 검색 청크 수 (작업 지시: 5~6).
RAG_CHUNK_LIMIT = 6
# 청크 1건당 컨텍스트에 넣을 최대 글자 수 — 과도한 토큰 폭증 방지.
_MAX_CHARS_PER_CHUNK = 1500
# 검색 타임아웃(초). 임베딩 모델이 콜드(배포 직후 ~33s)일 때 SSE 응답이
# 시작도 못 하고 막혀 500/502 가 나던 문제 방지 — 초과 시 일반 채팅으로 폴백.
# (모델 로드는 백그라운드 스레드에서 계속 진행되어 다음 요청부터 웜.)
RAG_SEARCH_TIMEOUT_S = 8.0


async def search_rag_context(
    query: str,
    *,
    limit: int = RAG_CHUNK_LIMIT,
) -> list[NasChunkHit]:
    """쿼리로 NAS 청크를 검색. 실패/지연해도 예외를 올리지 않고 빈 리스트 반환."""
    if not query or not query.strip():
        return []
    try:
        hits = await asyncio.wait_for(
            search_relevant_chunks(query=query, limit=limit),
            timeout=RAG_SEARCH_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "NAS RAG 검색 타임아웃(%.0fs) — 임베딩 콜드 추정, 일반 채팅으로 진행",
            RAG_SEARCH_TIMEOUT_S,
        )
        return []
    except Exception:  # noqa: BLE001 — 채팅을 막지 않도록 graceful.
        logger.warning("NAS RAG 검색 실패 — 일반 채팅으로 진행", exc_info=True)
        return []
    return [h for h in hits if (h.content or "").strip()]


def build_context_block(hits: list[NasChunkHit]) -> str:
    """검색 청크들을 system prompt 앞에 붙일 컨텍스트 텍스트로 포맷.

    형식: ``[출처: 파일경로]\n내용...`` 블록을 빈 줄로 구분.
    """
    if not hits:
        return ""
    parts: list[str] = [
        "아래는 회사 NAS 문서에서 검색된 참고 자료입니다. "
        "사용자 질문에 답할 때 관련 내용을 활용하고, 인용 시 출처 파일경로를 밝히세요. "
        "참고 자료에 없는 내용은 추측하지 말고 모른다고 답하세요.",
        "",
        "=== 참고 자료 시작 ===",
    ]
    for h in hits:
        source = h.file_path or h.file_name or "(경로 미상)"
        content = (h.content or "").strip()
        if len(content) > _MAX_CHARS_PER_CHUNK:
            content = content[:_MAX_CHARS_PER_CHUNK] + "..."
        parts.append(f"[출처: {source}]\n{content}")
        parts.append("")
    parts.append("=== 참고 자료 끝 ===")
    return "\n".join(parts)


def source_paths(hits: list[NasChunkHit]) -> list[str]:
    """프론트 표시용 출처 파일경로 목록 (중복 제거, 순서 유지)."""
    seen: set[str] = set()
    out: list[str] = []
    for h in hits:
        path = h.file_path or h.file_name
        if not path or path in seen:
            continue
        seen.add(path)
        out.append(path)
    return out
