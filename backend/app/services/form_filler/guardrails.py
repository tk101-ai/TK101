"""환각 방어 가드레일 (PRD NFR-04).

5개 방어선 중 코드 측 책임:
- #2 confidence 임계값 필터 (filter_low_confidence)
- #3 숫자/고유명사 토큰 인용 검증 (verify_token_grounding)
- #5 출처 메타 5종 (source_id, source_excerpt, llm_confidence, reasoning, variable_key) 강제

#1 (DB CHECK) 은 T5-A의 alembic 007이 form_mappings 테이블에 CHECK 제약으로 부여.
#4 (검수 강제 status flow) 는 routers/forms.py의 상태 전이 검사가 책임.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from dataclasses import dataclass

from app.config import settings

logger = logging.getLogger(__name__)

# 자료에 검증 가능한 토큰을 추출하는 정규식.
# - 숫자: 콤마/소수점 포함 (1,234.5)
# - 한글 고유명사 추정: 2~6자 한글 단어 + 직책/접미사 (예: 홍길동 대표, 동아제약)
# - 영문 고유명사: 대문자로 시작하는 1~5단어
_NUMBER_PATTERN = re.compile(r"-?\d{1,3}(?:[,]\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?")
_KOREAN_PROPER_PATTERN = re.compile(r"[가-힣]{2,6}(?:\s*(?:대표|회장|이사|팀장|매니저|주임)?)")
_ENGLISH_PROPER_PATTERN = re.compile(r"\b[A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){0,4}\b")

# JSON 파싱 시 LLM이 가끔 코드 펜스를 붙이는 경우 제거.
_JSON_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


@dataclass(frozen=True)
class GuardrailResult:
    """매핑 1건에 대한 검증 결과.

    accepted: 매핑이 그대로 저장 가능한지
    forced_value: accepted=False여도 None으로 강제 다운그레이드된 값 (저장 정책)
    reason: 검증 메시지 (감사 로그용)
    """

    accepted: bool
    forced_value: str | None
    reason: str


def strip_json_fences(text: str) -> str:
    """LLM 응답에서 ```json ... ``` 펜스를 안전하게 제거."""
    return _JSON_FENCE_PATTERN.sub("", text or "").strip()


def parse_strict_json(raw: str) -> dict:
    """LLM 응답을 strict JSON으로 파싱. 펜스 제거 + 첫 번째 { 부터 마지막 } 까지 best-effort.

    실패 시 ValueError. 호출자는 재시도 1회 후 폴백을 결정.
    """
    cleaned = strip_json_fences(raw)
    if not cleaned:
        raise ValueError("빈 응답")
    # 일부 모델이 prelude를 붙이는 경우 첫 { 와 마지막 } 사이만 발췌.
    first = cleaned.find("{")
    last = cleaned.rfind("}")
    if first == -1 or last == -1 or last <= first:
        raise ValueError("JSON 객체 경계 탐지 실패")
    snippet = cleaned[first : last + 1]
    return json.loads(snippet)


def is_uuid_like(value: str | None) -> bool:
    """source_id가 UUID 형식인지(또는 user_input/web_search 등 sentinel 값) 검사."""
    if value is None:
        return False
    if value in {"user_input", "web_search"}:
        # MVP에서는 user_input/web_search도 source_id 컬럼에 직접 들어올 수 있음.
        # 실제 row는 form_data_sources 테이블의 kind 별도 표현 — 호출자 매핑 책임.
        return True
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def filter_low_confidence(
    mapping: dict,
    *,
    threshold: float | None = None,
) -> tuple[bool, str]:
    """confidence < threshold 매핑은 자동 채움 거부 (PRD NFR-04 #2).

    Returns:
        (passed, reason)
    """
    limit = threshold if threshold is not None else settings.form_filler_min_confidence
    raw = mapping.get("llm_confidence")
    try:
        conf = float(raw)
    except (TypeError, ValueError):
        return False, f"confidence 필드 없음 또는 비숫자: {raw!r}"
    if conf < limit:
        return False, f"confidence {conf:.2f} < 임계 {limit:.2f}"
    return True, f"confidence {conf:.2f} >= 임계 {limit:.2f}"


def extract_grounding_tokens(value: str) -> list[str]:
    """value에서 grounding 검증 대상 토큰을 추출.

    - 숫자(콤마/소수점 포함)
    - 한글 고유명사 후보 (2~6자 한글)
    - 영문 PascalCase 고유명사 후보
    """
    if not value:
        return []
    tokens: list[str] = []
    tokens.extend(m.group(0) for m in _NUMBER_PATTERN.finditer(value))
    tokens.extend(m.group(0) for m in _KOREAN_PROPER_PATTERN.finditer(value))
    tokens.extend(m.group(0) for m in _ENGLISH_PROPER_PATTERN.finditer(value))
    # 중복 제거 + 너무 짧은 토큰(공백/단일 문자) 컷.
    return [t.strip() for t in dict.fromkeys(tokens) if len(t.strip()) >= 2]


def verify_token_grounding(value: str | None, source_excerpt: str | None) -> tuple[bool, str]:
    """value 안 숫자/고유명사 토큰이 source_excerpt 안에 존재하는지 검증 (PRD NFR-04 #3).

    완벽한 검사는 아님(LLM이 paraphrase한 경우 false positive 가능). MVP 정책:
    - 숫자 토큰은 1개라도 source_excerpt에 미존재하면 거부 (LLM이 임의 변형 가능성 高)
    - 한글/영문 고유명사 토큰은 50% 미만 일치 시 경고 (Phase 1에서 LLM-as-judge로 보강 예정)

    Returns:
        (passed, reason)
    """
    if value is None:
        return True, "value=null이라 토큰 검증 대상 아님"
    if not source_excerpt:
        return False, "source_excerpt 비어있음 — 검증 불가능"

    tokens = extract_grounding_tokens(value)
    if not tokens:
        return True, "검증 대상 토큰 없음(자유 텍스트)"

    excerpt_lower = source_excerpt.lower()
    # 숫자 토큰부터 검사 (변형 위험이 가장 큼).
    number_tokens = [t for t in tokens if _NUMBER_PATTERN.fullmatch(t)]
    for num in number_tokens:
        # 숫자는 콤마 유무 무관 비교 — "1,234"와 "1234" 모두 허용.
        normalized = num.replace(",", "")
        if normalized not in excerpt_lower.replace(",", ""):
            return False, f"숫자 토큰 '{num}' 가 source_excerpt에 없음"

    # 고유명사 토큰: 50% 일치 미달 시 거부.
    proper_tokens = [t for t in tokens if not _NUMBER_PATTERN.fullmatch(t)]
    if proper_tokens:
        hit = sum(1 for t in proper_tokens if t.lower() in excerpt_lower)
        if hit / len(proper_tokens) < 0.5:
            return False, f"고유명사 토큰 일치율 {hit}/{len(proper_tokens)} < 50%"
    return True, f"토큰 grounding OK (검사 {len(tokens)}개)"


def validate_mapping(
    mapping: dict,
    *,
    valid_source_ids: set[str],
    threshold: float | None = None,
) -> GuardrailResult:
    """단일 매핑 1건을 NFR-04 5개 방어선 중 코드 책임 영역(2/3/5) 모두 검증.

    Args:
        mapping: LLM이 반환한 매핑 dict
        valid_source_ids: form_data_sources에 등록된 source_id 화이트리스트
        threshold: confidence 임계값 (기본 settings)

    Returns:
        GuardrailResult — accepted=False면 forced_value=None으로 다운그레이드 후 저장.
    """
    variable_key = mapping.get("variable_key")
    if not variable_key or not isinstance(variable_key, str):
        return GuardrailResult(False, None, "variable_key 누락 또는 비문자열")

    value = mapping.get("value")
    source_id = mapping.get("source_id")

    # 방어선 #5: value가 있으면 source_id, source_excerpt, reasoning 모두 필수.
    if value is not None:
        if source_id is None:
            return GuardrailResult(False, None, "value 있으나 source_id null — 환각 의심")
        if not mapping.get("source_excerpt"):
            return GuardrailResult(False, None, "source_excerpt 누락")
        if not mapping.get("reasoning"):
            return GuardrailResult(False, None, "reasoning 누락")
        # 등록된 source_id 화이트리스트 일치 (LLM이 가짜 UUID를 만들어 낼 수 있음).
        if str(source_id) not in valid_source_ids:
            return GuardrailResult(
                False, None, f"source_id {source_id!r} 화이트리스트 외부 — 환각 의심"
            )

    # 방어선 #2: confidence 임계.
    passed, reason = filter_low_confidence(mapping, threshold=threshold)
    if not passed:
        return GuardrailResult(False, None, f"신뢰도 임계 미달: {reason}")

    # 방어선 #3: 토큰 grounding.
    if value is not None:
        passed, reason = verify_token_grounding(
            str(value), mapping.get("source_excerpt")
        )
        if not passed:
            return GuardrailResult(False, None, f"토큰 grounding 실패: {reason}")

    return GuardrailResult(True, value, "OK")


def sanitize_mappings(
    mappings: list[dict],
    *,
    valid_source_ids: set[str],
    threshold: float | None = None,
) -> tuple[list[dict], list[dict]]:
    """매핑 리스트를 검증해 (저장 가능, 누락 보강 큐) 두 그룹으로 분할.

    저장 그룹: GuardrailResult.accepted == True
    누락 보강 큐: 거부 사유와 함께 value=null로 다운그레이드된 항목

    이 함수는 새 리스트만 반환하며 입력을 mutate하지 않는다 (불변성 원칙).
    """
    accepted: list[dict] = []
    rejected: list[dict] = []
    for original in mappings:
        result = validate_mapping(
            original, valid_source_ids=valid_source_ids, threshold=threshold
        )
        if result.accepted:
            accepted.append(dict(original))
            continue
        # 거부된 매핑은 value/source_id를 null로 다운그레이드해 누락 보강 큐로.
        downgraded = dict(original)
        downgraded["value"] = None
        downgraded["source_id"] = None
        downgraded["source_excerpt"] = None
        downgraded["_guardrail_reason"] = result.reason
        logger.info(
            "매핑 가드레일 거부: variable_key=%s reason=%s",
            original.get("variable_key"),
            result.reason,
        )
        rejected.append(downgraded)
    return accepted, rejected
