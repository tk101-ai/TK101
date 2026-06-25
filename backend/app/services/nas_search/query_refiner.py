"""docgen 자유지시문 → NAS 의미검색용 핵심 쿼리 정제.

docgen 의 `topic` 은 "이거랑 나스에서 신세계 서버 증설 관련 자료 찾아서 보고서 써줘"
같은 **자유 지시문**이다. 이걸 그대로 의미검색 쿼리로 쓰면 "찾아서/작성/보고서/써줘"
같은 지시·형식·지시대명사 토큰이 임베딩에 섞여 주제어 비중을 떨어뜨리고(검색·리랭크
품질↓), 어제 운영에서 "서버 증설" 의도가 엉뚱한 문서(신세계 홈페이지)와 매칭되는
원인이 됐다. 여기서 핵심 주제어만 한 줄로 뽑아 **검색 입력**으로 쓴다.

문서 생성 자체는 원본 지시문(topic)을 그대로 쓰므로 이 정제는 검색에만 영향하고
생성 결과 내용은 바뀌지 않는다. 저비용 Haiku 1회(temperature=0). 비활성/짧은
지시문/LLM 실패/이상 출력 시에는 원본 지시문으로 폴백해 검색이 멈추지 않게 한다.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.services.llm.client import call_claude

logger = logging.getLogger(__name__)

# 이 길이 미만의 지시문은 이미 키워드성(예: "마케팅 전략") → 정제 LLM 호출을 생략하고
# 원본을 그대로 쓴다(불필요한 호출·지연 방지).
_REFINE_MIN_CHARS = 16
# 정제 결과가 비정상적으로 길면(요약 실패/잡담 혼입) 신뢰하지 않고 원본으로 폴백한다.
_REFINE_MAX_OUTPUT_CHARS = 200
# 핵심어 한 줄이면 충분 — 출력 토큰 상한을 낮게 잡아 비용·지연을 묶는다.
_REFINE_MAX_TOKENS = 80

_SYSTEM_PROMPT = (
    "너는 문서작성 지시문에서 사내 자료 의미검색에 쓸 핵심 검색어만 뽑는 도구다.\n"
    "규칙:\n"
    "- 주제어·고유명사·핵심 개념어만 공백으로 구분해 한 줄로 출력한다.\n"
    "- '작성/써줘/만들어/정리/보고서/제안서/계획서/찾아서/검색/나스에서/이거/그거' 같은\n"
    "  지시·형식·지시대명사 토큰은 제거한다.\n"
    "- 지시문에 실제로 있는 표현만 쓴다(새 단어·번역·부연 금지).\n"
    "- 설명·따옴표·머리말 없이 검색어만 출력한다."
)


def refine_search_query(instruction: str) -> str:
    """자유 지시문에서 NAS 검색용 핵심 쿼리를 추출(실패 시 원본 폴백).

    동기 함수 — 호출부(collect_sources)가 asyncio.to_thread 로 감싼다(call_claude 는
    블로킹 HTTP). 어떤 예외도 밖으로 던지지 않고 원본 지시문을 반환해, 검색 자체가
    정제 실패로 막히지 않게 한다.
    """
    text = (instruction or "").strip()
    if not settings.docgen_query_refine_enabled:
        return text
    if len(text) < _REFINE_MIN_CHARS:
        return text

    try:
        resp = call_claude(
            system_prompt=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
            model=settings.docgen_query_refine_model or settings.form_filler_haiku_model,
            max_tokens=_REFINE_MAX_TOKENS,
            temperature=0,
            cache_system=True,
            trace_name="docgen_query_refine",
        )
    except Exception:  # noqa: BLE001 — 정제 실패가 검색을 막아선 안 됨(원본 폴백).
        logger.exception("검색 쿼리 정제 실패 — 원본 지시문으로 검색")
        return text

    refined = (resp.text or "").strip()
    # 빈 출력/과도 출력(잡담 혼입)은 신뢰하지 않고 원본으로 폴백.
    if not refined or len(refined) > _REFINE_MAX_OUTPUT_CHARS:
        logger.warning(
            "검색 쿼리 정제 결과 비정상(len=%d) — 원본 폴백", len(refined)
        )
        return text

    logger.info("검색 쿼리 정제: %r → %r", text[:60], refined[:60])
    return refined
