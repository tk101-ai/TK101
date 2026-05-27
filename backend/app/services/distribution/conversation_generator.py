"""대화 생성 엔진 — Claude 호출 + JSON 검증 + 재시도 (T9 PRD Phase 2).

흐름:
1. ``build_prompt`` (scenario_engine) 로 프롬프트 생성.
2. ``call_claude`` (form_filler.llm_client 재사용) 로 Sonnet 4.6 호출.
3. JSON 추출 + pydantic 검증.
4. 검증 실패 시 ``distribution_send_retry_max`` 만큼 재시도 (다른 temperature).
5. 검증된 메시지 리스트 + 비용/토큰 메트릭 반환.

호출자 (라우터) 는 결과를 distribution_sessions / distribution_messages 에 저장.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from app.config import settings
from app.services.distribution.scenario_engine import (
    BlContext,
    ConversationPrompt,
    Language,
    PersonaContext,
    ScenarioContext,
    TimingProfile,
    build_prompt,
    extract_messages_from_response,
)
from app.services.form_filler.llm_client import LLMResponse, call_claude

logger = logging.getLogger(__name__)


# Claude 응답 1메시지에 대한 검증 스키마 — scenario_engine 의 OUTPUT_SCHEMA_DOC 과 매치.
class _GeneratedMessage(BaseModel):
    sender: str = Field(min_length=1, max_length=20)
    content: str = Field(min_length=1, max_length=2000)
    send_after_sec: int = Field(ge=0, le=86400)  # 0초 ~ 24시간
    typing_sec: int = Field(default=3, ge=0, le=60)


@dataclass(frozen=True)
class GenerationResult:
    """대화 생성 1회 결과. 호출자가 DB 에 매핑하여 저장."""

    messages: list[_GeneratedMessage]
    raw_text: str  # 디버깅용 원본 응답
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str
    attempts: int  # 실제 호출 횟수 (재시도 포함)
    trace_id: str | None


class GenerationError(RuntimeError):
    """대화 생성 실패 — Claude 응답이 검증을 통과하지 못함 (재시도 한도 초과)."""


def _validate_messages(
    raw_msgs: list[dict[str, Any]],
    *,
    valid_senders: set[str],
) -> list[_GeneratedMessage]:
    """pydantic 검증 + sender 가 페르소나 라벨에 속하는지 검사."""
    if not raw_msgs:
        raise ValueError("messages 리스트가 비어있음")
    if len(raw_msgs) > 50:
        raise ValueError(f"messages 개수 비정상: {len(raw_msgs)}")
    validated: list[_GeneratedMessage] = []
    for idx, raw in enumerate(raw_msgs):
        msg = _GeneratedMessage.model_validate(raw)
        if msg.sender not in valid_senders:
            raise ValueError(
                f"messages[{idx}].sender={msg.sender!r} 가 페르소나에 없음. "
                f"허용: {sorted(valid_senders)}"
            )
        validated.append(msg)
    return validated


def generate_conversation(
    *,
    scenario: ScenarioContext,
    sender: PersonaContext,
    receiver: PersonaContext,
    bl: BlContext | None = None,
    max_attempts: int | None = None,
    base_temperature: float = 0.8,
    timing_profile: TimingProfile = "normal",
    language: Language = "ko",
) -> GenerationResult:
    """Claude 호출하여 대화 1세트 생성.

    - 첫 시도는 ``base_temperature`` (보통 0.8 — 약간 창의적).
    - 재시도 시 temperature 살짝 변형 (0.7 / 0.9 등) — 같은 응답 반복 회피.
    - 모든 재시도 실패 시 ``GenerationError``.
    - ``timing_profile`` 로 메시지 간격 분포 결정 (short/normal/varied).
    - ``language`` 로 대화 언어 결정 (ko/zh) — build_prompt 에 전달.
    """
    if max_attempts is None:
        max_attempts = max(1, settings.distribution_send_retry_max)

    prompt: ConversationPrompt = build_prompt(
        scenario=scenario,
        sender=sender,
        receiver=receiver,
        bl=bl,
        timing_profile=timing_profile,
        language=language,
    )
    valid_senders = {sender.account_label, receiver.account_label}

    last_error: Exception | None = None
    total_input = 0
    total_output = 0
    total_cost = 0.0
    last_response: LLMResponse | None = None
    last_raw_text = ""

    for attempt in range(1, max_attempts + 1):
        # 재시도마다 temperature 0.05 씩 흔들어 다양성 확보.
        temp_offset = (attempt - 1) * 0.05
        temperature = max(0.1, min(1.0, base_temperature - temp_offset))

        # call_claude 는 messages 파라미터에 list[dict] 받음 (Anthropic 형식).
        try:
            response = call_claude(
                system_prompt=prompt.system,
                messages=[{"role": "user", "content": prompt.user_content}],
                model=settings.distribution_claude_model,
                max_tokens=2048,
                cache_system=True,
                trace_name="distribution_conversation",
                trace_metadata={
                    "scenario": scenario.name,
                    "trigger": scenario.trigger_event,
                    "sender": sender.account_label,
                    "receiver": receiver.account_label,
                    "temperature": temperature,
                    "attempt": attempt,
                    "language": language,
                },
            )
        except RuntimeError as exc:
            # Claude API 키 없음 / SDK 미설치 — 재시도 무의미.
            raise GenerationError(f"Claude 호출 자체 실패: {exc}") from exc

        last_response = response
        last_raw_text = response.text
        total_input += response.input_tokens
        total_output += response.output_tokens
        total_cost += response.cost_usd

        try:
            raw_msgs = extract_messages_from_response(response.text)
            validated = _validate_messages(raw_msgs, valid_senders=valid_senders)
            # 성공.
            return GenerationResult(
                messages=validated,
                raw_text=response.text,
                input_tokens=total_input,
                output_tokens=total_output,
                cost_usd=round(total_cost, 6),
                model=response.model,
                attempts=attempt,
                trace_id=response.trace_id,
            )
        except (ValueError, ValidationError) as exc:
            last_error = exc
            logger.warning(
                "distribution.generate attempt %d 실패: %s",
                attempt,
                exc,
            )
            # 마지막 시도가 아니면 약간 대기 후 재시도 (Claude 측 transient 회피).
            if attempt < max_attempts:
                time.sleep(0.5)

    # 모든 재시도 실패.
    raise GenerationError(
        f"대화 생성 {max_attempts}회 모두 실패. 마지막 오류: {last_error}. "
        f"raw_text 앞부분: {last_raw_text[:200]!r}"
    )
