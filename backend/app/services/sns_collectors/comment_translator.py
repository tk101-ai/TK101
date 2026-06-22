"""SNS 댓글 다국어 → 한국어 번역 (Claude Haiku).

서울시 글로벌 SNS 채널 특성상 댓글이 영어/벵골어/아랍어/중국어 등 다국어로 달린다.
마케팅 담당자가 내용을 파악할 수 있도록 한국어로 번역한다.

- 조회 시 on-demand 번역. 원문(text)은 보존하고 번역문만 translated_text 에 캐시.
- 배치(JSON) 호출로 여러 댓글을 한 번에 번역해 비용/지연을 줄인다.
- 이미 한국어인 댓글도 그대로 한국어로 반환(모델이 식별).

비용: Haiku 4.5, 배치당 1회. 입력 길이 cap.
"""
from __future__ import annotations

import asyncio
import json
import logging

from app.services.llm.client import call_claude

logger = logging.getLogger(__name__)

HAIKU_MODEL = "claude-haiku-4-5-20251001"
# 한 번의 호출에 묶을 최대 댓글 수 / 입력 길이 cap.
BATCH_SIZE = 40
MAX_INPUT_CHARS = 16_000
MAX_OUTPUT_TOKENS = 4_000

SYSTEM_PROMPT = (
    "당신은 소셜미디어 댓글 번역기입니다. 입력은 JSON 으로 주어진 댓글 목록입니다. "
    "각 댓글의 원문을 자연스러운 한국어로 번역하세요. "
    "규칙: ①이미 한국어면 그대로 두세요. ②이모지/기호만 있으면 원문 그대로 두세요. "
    "③의미를 지어내지 말고 직역에 가깝게, 단 자연스럽게. ④고유명사·해시태그·멘션은 유지. "
    "반드시 입력과 같은 i 값을 갖는 JSON 만 출력하세요. 다른 설명은 출력하지 마세요. "
    'JSON 형식: {"translations":[{"i":0,"t":"번역문"}, ...]}'
)


def _parse_translations(response_text: str) -> dict[int, str]:
    """모델 응답(JSON)에서 {i: 번역문} 매핑을 추출. 코드펜스/잡텍스트에 견고하게."""
    text = (response_text or "").strip()
    if not text:
        return {}
    # 코드펜스 제거.
    if text.startswith("```"):
        text = text.strip("`")
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1 :]
    # 첫 '{' ~ 마지막 '}' 구간만.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return {}
    try:
        data = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return {}
    out: dict[int, str] = {}
    for item in data.get("translations") or []:
        if not isinstance(item, dict):
            continue
        idx = item.get("i")
        translated = item.get("t")
        if isinstance(idx, int) and isinstance(translated, str):
            out[idx] = translated.strip()
    return out


def _call_haiku_sync(batch: list[tuple[int, str]]) -> dict[int, str]:
    """배치(인덱스, 원문) → {인덱스: 번역문}. 실패 시 빈 dict."""
    payload = {"comments": [{"i": idx, "t": text} for idx, text in batch]}
    user_content = (
        "다음 댓글들을 한국어로 번역하세요.\n"
        + json.dumps(payload, ensure_ascii=False)
    )
    response = call_claude(
        system_prompt=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
        model=HAIKU_MODEL,
        max_tokens=MAX_OUTPUT_TOKENS,
        cache_system=False,
        trace_name="sns_comment_translator",
    )
    return _parse_translations(response.text)


def _chunk(items: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """BATCH_SIZE 개수 + MAX_INPUT_CHARS 길이 양쪽으로 청크 분할."""
    chunks: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    total = 0
    for idx, text in items:
        length = len(text)
        if current and (len(current) >= BATCH_SIZE or total + length > MAX_INPUT_CHARS):
            chunks.append(current)
            current = []
            total = 0
        current.append((idx, text))
        total += length
    if current:
        chunks.append(current)
    return chunks


async def translate_to_korean(texts: list[str]) -> list[str | None]:
    """원문 리스트 → 한국어 번역 리스트(입력과 동일 길이/순서).

    - 빈/공백 텍스트는 번역 대상이 아니므로 None.
    - 번역 실패한 항목도 None (caller 가 원문 유지/재시도).
    blocking Anthropic 호출이라 to_thread 로 이벤트 루프 분리.
    """
    result: list[str | None] = [None] * len(texts)
    targets: list[tuple[int, str]] = [
        (i, t.strip()) for i, t in enumerate(texts) if t and t.strip()
    ]
    if not targets:
        return result

    for chunk in _chunk(targets):
        try:
            mapping = await asyncio.to_thread(_call_haiku_sync, chunk)
        except Exception:  # noqa: BLE001 — 배치 실패는 격리, 나머지 배치 진행
            logger.exception("댓글 번역 배치 실패 (%d건)", len(chunk))
            continue
        for idx, _ in chunk:
            translated = mapping.get(idx)
            if translated:
                result[idx] = translated
    return result
