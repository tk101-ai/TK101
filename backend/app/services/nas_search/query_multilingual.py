"""채팅 대화 메시지 → 다국어(KO/ZH/EN) 의미검색 쿼리 확장 (2026-07-01).

Qwen3 임베딩 공유공간의 **same-language 편향** 때문에 한국어 쿼리는 한국어 문서만
후보 풀에 담고 중문·영문 자료(웨이보·샤오홍슈 등 코퍼스의 대다수)를 아예 못
끌어온다(2026-07-01 실측: KO 쿼리 top10 = KO 10/ZH 0, 같은 개념을 ZH로 치면 ZH
문서가 상위에 나옴 → 결과집합이 언어별로 분리). 후보 풀 단계의 편향이라 뒷단
리랭커로도 못 살린다.

여기서 대화 메시지의 핵심 검색어를 뽑아 KO/ZH/EN 로 번역한 변형 목록을 만든다.
각 변형이 자기 언어 문서 풀을 검색하고 bridge 가 RRF(순위기반)로 병합한다. 저비용
Haiku 1회(temperature=0, JSON). 실패/타임아웃/이상출력 시 원문 단일 쿼리로 폴백해
검색이 멈추지 않게 한다(graceful).
"""
from __future__ import annotations

import json
import logging
import re

from app.config import settings
from app.services.llm.client import call_claude

logger = logging.getLogger(__name__)

# 핵심어 3언어면 충분 — 출력 토큰 상한을 낮게 잡아 비용·지연을 묶는다.
_MAX_TOKENS = 150
# 언어당 검색어가 비정상적으로 길면(요약 실패/본문 혼입) 신뢰하지 않고 버린다.
_MAX_LANG_CHARS = 200

_SYSTEM_PROMPT = (
    "너는 사내 문서 의미검색을 위해 대화 메시지에서 핵심 검색어를 뽑고 여러 언어로\n"
    "번역하는 도구다. 사내 문서는 한국어·중국어(간체)·영어가 섞여 있어, 같은 주제라도\n"
    "각 언어 문서를 모두 찾으려면 검색어가 언어별로 필요하다.\n"
    "규칙:\n"
    "- 먼저 메시지에서 주제어·고유명사·핵심 개념어만 뽑는다(지시·잡담·형식 토큰 제거:\n"
    "  '찾아줘/알려줘/정리/보고서/이거/간략하게' 등).\n"
    "- 그 핵심어를 ko(한국어), zh(중국어 간체), en(영어) 세 언어로 각각 번역해 공백으로\n"
    "  구분한 한 줄 검색어로 만든다. 브랜드·고유명사는 각 언어의 통용 표기를 쓴다.\n"
    "- 설명·머리말 없이 아래 JSON 한 줄만 출력한다:\n"
    '  {"ko": "...", "zh": "...", "en": "..."}'
)


def _parse_json_obj(text: str) -> dict | None:
    """LLM 출력에서 첫 JSON 오브젝트를 관대하게 추출(코드펜스·머리말 허용)."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except (json.JSONDecodeError, ValueError):
        return None
    return obj if isinstance(obj, dict) else None


def _dedupe(queries: list[str]) -> list[str]:
    """공백/대소문자 정규화로 중복 검색어 제거(순서 유지)."""
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = re.sub(r"\s+", " ", q).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(q.strip())
    return out


def expand_query_multilingual(message: str) -> list[str]:
    """대화 메시지 → 다국어 검색어 목록[ko, zh, en] (실패 시 [원문] 폴백).

    동기 함수 — 호출부가 asyncio.to_thread + wait_for 로 감싼다(call_claude 는 블로킹
    HTTP). 어떤 예외도 밖으로 던지지 않고 원문 단일 쿼리를 반환해, 검색이 확장 실패로
    막히지 않게 한다.
    """
    text = (message or "").strip()
    if not text:
        return []
    if not settings.nas_multilingual_query_enabled:
        return [text]

    langs = settings.nas_multilingual_query_lang_list or ["ko"]
    try:
        resp = call_claude(
            system_prompt=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": text}],
            model=(
                settings.nas_multilingual_query_model
                or settings.form_filler_haiku_model
            ),
            max_tokens=_MAX_TOKENS,
            temperature=0,
            cache_system=True,
            trace_name="nas_multilingual_query",
        )
    except Exception:  # noqa: BLE001 — 확장 실패가 검색을 막아선 안 됨(원문 폴백).
        logger.exception("다국어 쿼리 확장 실패 — 원문으로 검색")
        return [text]

    obj = _parse_json_obj(resp.text or "")
    if not obj:
        logger.warning("다국어 쿼리 확장 출력 파싱 실패 — 원문 폴백")
        return [text]

    variants: list[str] = []
    for lang in langs:
        val = str(obj.get(lang) or "").strip()
        if val and len(val) <= _MAX_LANG_CHARS:
            variants.append(val)
    variants = _dedupe(variants)
    if not variants:
        return [text]
    logger.info("다국어 쿼리 확장: %r → %s", text[:50], variants)
    return variants
