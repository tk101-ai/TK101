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

from app.config import settings
from app.services.nas_search.bridge import (
    NasChunkHit,
    search_relevant_chunks,
    search_relevant_chunks_multilingual,
)
from app.services.nas_search.query_multilingual import expand_query_multilingual
from app.services.nas_search.query_refiner import refine_search_query

logger = logging.getLogger(__name__)

# RAG 검색 청크 수. 채팅은 LLM 이 청크를 전부 읽으므로 정밀 순위(리랭크)보다
# 커버리지가 중요 → 리랭크 없이 벡터 top-N 을 넉넉히 준다(아래 rerank=False).
RAG_CHUNK_LIMIT = 10
# 청크 1건당 컨텍스트에 넣을 최대 글자 수 — 과도한 토큰 폭증 방지.
_MAX_CHARS_PER_CHUNK = 1500
# 검색 타임아웃(초). 임베딩 모델이 콜드(배포 직후 ~33s)일 때 SSE 응답이
# 시작도 못 하고 막혀 500/502 가 나던 문제 방지 — 초과 시 일반 채팅으로 폴백.
# (모델 로드는 백그라운드 스레드에서 계속 진행되어 다음 요청부터 웜.)
RAG_SEARCH_TIMEOUT_S = 8.0
# 대화 메시지 → 검색어 정제 타임아웃(초). Haiku 1회(~1-2s) + 자체 폴백.
RAG_REFINE_TIMEOUT_S = 5.0
# 컨텍스트에 한 파일이 차지할 최대 청크 수. 같은 보고서에서 인접 청크가 top-N을
# 독점해 다른 출처가 묻히는 것을 막아 출처 다양성을 높인다(리랭크 제거 후 보완).
RAG_PER_FILE_CAP = 3


def _cap_per_file(hits: list[NasChunkHit], cap: int = RAG_PER_FILE_CAP) -> list[NasChunkHit]:
    """파일경로별 청크 수를 ``cap`` 으로 제한(점수 순서 유지). 한 파일 독점 방지."""
    counts: dict[str, int] = {}
    out: list[NasChunkHit] = []
    for h in hits:
        key = h.file_path or h.file_name or ""
        n = counts.get(key, 0)
        if n >= cap:
            continue
        counts[key] = n + 1
        out.append(h)
    return out


async def _refine_query(message: str) -> str:
    """대화 메시지에서 의미검색용 핵심 검색어 정제.

    채팅 메시지는 "회사 소개서 관련된 내용 찾아줄 수 있을까? 간략하게만" 처럼
    지시·잡담 토큰이 섞여 그대로 임베딩하면 주제어 비중이 떨어져 엉뚱한 문서가
    매칭된다(운영 확인). docgen 과 동일한 정제기로 주제어만 뽑아 검색 품질을 높인다.
    실패/타임아웃 시 원문으로 폴백.
    """
    try:
        refined = await asyncio.wait_for(
            asyncio.to_thread(refine_search_query, message),
            timeout=RAG_REFINE_TIMEOUT_S,
        )
        return (refined or message).strip() or message
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001 — 정제 실패가 검색 막지 않게.
        return message


async def _expand_query(message: str) -> list[str]:
    """대화 메시지 → 다국어(KO/ZH/EN) 검색어 변형 목록.

    Qwen3 임베딩의 same-language 편향(한국어 쿼리가 중문·영문 문서를 후보 풀에
    못 담음)을 우회하기 위해 언어별 검색어를 만든다. 실패/타임아웃 시 정제된 원문
    단일 쿼리로 폴백해 검색이 멈추지 않게 한다(refine 과 동일한 graceful 원칙).
    """
    try:
        variants = await asyncio.wait_for(
            asyncio.to_thread(expand_query_multilingual, message),
            timeout=RAG_REFINE_TIMEOUT_S,
        )
        return variants or [await _refine_query(message)]
    except (asyncio.TimeoutError, Exception):  # noqa: BLE001 — 확장 실패가 검색 막지 않게.
        return [await _refine_query(message)]


async def search_rag_context(
    query: str,
    *,
    limit: int = RAG_CHUNK_LIMIT,
) -> list[NasChunkHit]:
    """쿼리로 NAS 청크를 검색. 실패/지연해도 예외를 올리지 않고 빈 리스트 반환.

    검색 전에 대화 메시지를 핵심 검색어로 정제한다(장황한 원문 → 키워드).
    """
    if not query or not query.strip():
        return []
    try:
        # 다국어 확장 ON: 대화 메시지를 KO/ZH/EN 검색어로 확장해 각 언어 풀을 검색하고
        # RRF 로 병합한다(중문·영문 자료가 한국어 쿼리에 묻히는 same-language 편향 우회).
        # OFF: 기존처럼 핵심어 정제 후 단일 raw-cosine 검색.
        # 두 경로 모두 rerank=False — CPU 리랭커(~8s)는 채팅을 크게 지연시키고, 애초에
        # 후보 풀에 없는 타언어 문서는 리랭크로도 못 살린다(2026-07-01 실측). 파일당
        # 상한 적용 후에도 limit 을 채우도록 후보를 넉넉히(2배) 가져온다.
        if settings.nas_multilingual_query_enabled:
            variants = await _expand_query(query)
            logger.info("RAG 다국어 검색어: %s", variants)
            hits = await asyncio.wait_for(
                search_relevant_chunks_multilingual(queries=variants, limit=limit * 2),
                timeout=RAG_SEARCH_TIMEOUT_S,
            )
        else:
            search_query = await _refine_query(query)
            if search_query != query:
                logger.info("RAG 쿼리 정제: %r → %r", query[:50], search_query[:50])
            hits = await asyncio.wait_for(
                search_relevant_chunks(
                    query=search_query, limit=limit * 2, rerank=False
                ),
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
    nonempty = [h for h in hits if (h.content or "").strip()]
    return _cap_per_file(nonempty)[:limit]


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
