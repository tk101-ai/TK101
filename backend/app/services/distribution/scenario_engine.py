"""시나리오 → Claude 프롬프트 변환 (T9 PRD 6-3).

핵심 책임:
- 시나리오 비트 + 페르소나 톤 + BL 컨텍스트 + few-shot 예시 → Claude 프롬프트로 직렬화
- 출력 JSON 스키마 정의 (conversation_generator 가 같이 사용)

AI 티 제거 규칙은 system 프롬프트에 명시. 페르소나 톤 프로필이 핵심.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo


# 메시지 간격 분포 프로파일 (T9 — 2026-05-26).
TimingProfile = Literal["short", "normal", "varied"]

_TIMING_GUIDES: dict[str, str] = {
    "short": (
        "[메시지 간격 가이드 — short / 빠른 핑퐁]\n"
        "- 메시지 사이 간격(send_after_sec)은 30초 ~ 30분 사이로 짧게 두세요.\n"
        "- 거의 즉시 응답하는 채팅 페이스. 첫 메시지는 0초, 이후는 30~1800초 범위에서 분포.\n"
        "- 한 명이 연속으로 짧게 분할 송신할 때는 30초~3분 정도로 묶어서 보냅니다."
    ),
    "normal": (
        "[메시지 간격 가이드 — normal / 일상 비즈니스]\n"
        "- 메시지 사이 간격은 5분 ~ 3시간(=180~10800초) 사이에서 자연스럽게 혼합하세요.\n"
        "- 첫 메시지는 0초, 이후는 평균 20~40분 간격이지만 짧은 즉답과 1~3시간 텀이 섞이도록.\n"
        "- 너무 일정한 간격(예: 모두 5분, 모두 10분)은 부자연스럽습니다 — 반드시 폭넓게 분산."
    ),
    "varied": (
        "[메시지 간격 가이드 — varied / 하루를 거쳐가는 흐름]\n"
        "- 의도적으로 폭넓은 간격: 1분 즉답과 3~12시간(180~43200초) 후 답장이 섞여야 합니다.\n"
        "- 시나리오가 짧아도 좋으니 '오전에 말 걸고 오후/저녁에 답장' 같은 패턴을 만드세요.\n"
        "- 발신자가 정보 분할로 연속 송신할 땐 짧게, 상대방의 응답엔 의도적으로 큰 텀을 두세요.\n"
        "- 한 메시지라도 send_after_sec 가 14400(4시간) 이상인 경우가 최소 1건은 포함되어야 합니다."
    ),
}


def timing_guide(profile: TimingProfile) -> str:
    """profile 에 해당하는 시간 분포 가이드 텍스트 반환."""
    return _TIMING_GUIDES.get(profile, _TIMING_GUIDES["normal"])


# Claude 응답 JSON 스키마. conversation_generator 가 검증에 사용.
# pydantic 으로 강제 검증하므로 schema 정의는 system 프롬프트에 평문 명시만.
OUTPUT_SCHEMA_DOC = """\
응답은 JSON 객체로만 반환하세요. 다른 텍스트나 설명을 추가하지 마세요.

스키마:
{
  "messages": [
    {
      "sender": "<account_label, 예: KR-A1>",
      "content": "<메시지 본문, 1~2문장>",
      "send_after_sec": <이전 메시지 송신 후 초, 정수>,
      "typing_sec": <타이핑 시뮬레이션 초, 정수, 보통 2~8>
    },
    ...
  ]
}

메시지 개수: 5~14개 사이.
"""

# AI 티 제거 강제 규칙. 시나리오 무관 공통.
ANTI_AI_RULES = """\
다음 규칙을 절대 어기지 마세요:

[금지 표현]
- "도움이 되었으면 좋겠습니다", "확실히 알려드리겠습니다", "필요하시면 언제든"
- 너무 정확한 시간 표기 ("정확히 3시 47분에" 등)
- 영어 비즈니스 표현 직역 ("아래와 같이", "상기 내용", "본 건")
- 과도하게 정중한 문어체 ("~하셨음을 알려드립니다")

[스몰토크·안부 인사 금지]
- "안녕하세요", "수고하세요", "잘 지내시죠" 같은 안부 인사로 대화를 시작하지 마세요.
- 날씨·주말·식사·건강 같은 잡담은 절대 넣지 마세요. 본론만 다룹니다.
- 첫 메시지는 곧바로 본론(시나리오 첫 비트의 핵심)으로 시작합니다.
- 마무리 인사("감사합니다 수고하세요~" 등 한두 마디)는 비트가 명시한 경우에만 짧게.

[필수 표현]
- 한 메시지는 1~2문장만. 길면 분할.
- 끝맺음에 "~", "요", "넵", "감사합니다" 같은 한국 채팅 특유 표현 자주 사용
- 가끔 줄임말 ("그러면" → "그럼", "있습니다" → "있어요")
- 3% 확률로 의도된 가벼운 오타 (한 글자만 빠지거나 자음 빠뜨림)
- 시간 흐름이 자연스럽게 — 첫 메시지 후 5분~수시간 간격 혼합

[메시지 분할 패턴]
- 발신자가 정보 여러개 줄 때: 짧게 여러 메시지로 나눠서. 한 번에 다 안 보냄.
- 수신자는 보통 더 짧고 단정한 응답. 가끔 즉답, 가끔 한참 뒤 답.

[톤 일관성]
- 페르소나 톤 프로필을 절대 어기지 말 것.
- 두 페르소나의 어조가 미세하게 달라야 함 (한쪽은 약간 더 짧고, 한쪽은 약간 더 정보 주도).
"""


@dataclass(frozen=True)
class PersonaContext:
    """프롬프트 생성에 필요한 페르소나 핵심 정보."""

    account_label: str
    role: str
    display_name: str
    tone_profile: dict[str, Any] | None


@dataclass(frozen=True)
class ScenarioContext:
    """시나리오 + 비트.

    참고: 여러 시나리오를 하나의 대화로 합성하려면 ``merge_scenario_contexts`` 사용.
    합성된 ScenarioContext 는 beats 의 intent 앞에 ``[시나리오명]`` 접두어가 붙어
    LLM 이 주제 전환 시점을 인식할 수 있도록 구성된다.
    """

    name: str
    trigger_event: str
    beats: list[dict[str, Any]]
    example_msgs: list[dict[str, Any]] | None
    raw_text: str | None


def merge_scenario_contexts(
    scenarios: list[ScenarioContext],
    *,
    name: str = "통합 주간 대화",
) -> ScenarioContext:
    """N개 시나리오의 beats + example_msgs 를 하나로 합쳐 새 ScenarioContext 반환.

    동작:
    - name: 합성 시나리오 표시명.
    - trigger_event: 첫 시나리오의 trigger_event.
    - beats: 모든 시나리오의 beats 를 순차 concat. step 번호 1부터 재부여.
      각 비트 intent 앞에 ``[시나리오 이름]`` 접두어 추가하여 LLM 이 주제 전환을 인식.
    - example_msgs: 모든 시나리오의 example_msgs 를 concat. 발신자 라벨은 그대로.
    - raw_text: scenarios 의 raw_text 를 줄바꿈+구분선으로 join.

    호환성:
    - scenarios 길이가 1 이면 입력 시나리오를 그대로 반환 (불필요한 접두어 회피).
    - 빈 리스트는 ``ValueError``.
    """
    if not scenarios:
        raise ValueError("scenarios 비어있음")
    if len(scenarios) == 1:
        return scenarios[0]

    merged_beats: list[dict[str, Any]] = []
    step_idx = 1
    for sc in scenarios:
        for beat in sc.beats:
            merged_beats.append(
                {
                    "step": step_idx,
                    "intent": f"[{sc.name}] {beat.get('intent', '')}",
                    "tone_hint": beat.get("tone_hint"),
                }
            )
            step_idx += 1

    merged_examples: list[dict[str, Any]] = []
    for sc in scenarios:
        if sc.example_msgs:
            merged_examples.extend(sc.example_msgs)

    merged_raw = "\n\n---\n\n".join(
        sc.raw_text or "" for sc in scenarios if sc.raw_text
    ) or None

    return ScenarioContext(
        name=name,
        trigger_event=scenarios[0].trigger_event,
        beats=merged_beats,
        example_msgs=merged_examples if merged_examples else None,
        raw_text=merged_raw,
    )


@dataclass(frozen=True)
class BlContext:
    """BL 레코드 컨텍스트. 없을 수 있음 (수동 트리거)."""

    bl_number: str | None
    container_no: str | None
    product: str | None
    quantity: int | None
    departure_date: date | None
    arrival_date: date | None
    destination: str | None


@dataclass(frozen=True)
class ConversationPrompt:
    """Claude 호출용 프롬프트 페이로드."""

    system: str
    user_content: str


def _format_tone_profile(profile: dict[str, Any] | None) -> str:
    """톤 프로필을 사람이 읽기 좋은 텍스트로 직렬화."""
    if not profile:
        return "(특별한 톤 지시 없음 — 기본 한국 비즈니스 채팅 어조)"
    lines: list[str] = []
    if "formality" in profile:
        v = profile["formality"]
        lvl = "친근함" if v < 0.4 else "보통" if v < 0.7 else "정중함"
        lines.append(f"- 격식 수준: {lvl} ({v})")
    if "emoji_freq" in profile:
        lines.append(f"- 이모지 빈도: {profile['emoji_freq']} (0=절대 안 씀, 1=매우 자주)")
    if "typo_rate" in profile:
        lines.append(f"- 오타 비율: {profile['typo_rate']} (자연스러운 의도된 오타)")
    if "common_phrases" in profile:
        phrases = profile["common_phrases"]
        if isinstance(phrases, list) and phrases:
            lines.append(f"- 자주 쓰는 표현: {', '.join(phrases)}")
    if "preferred_endings" in profile:
        endings = profile["preferred_endings"]
        if isinstance(endings, list) and endings:
            lines.append(f"- 선호 어미: {', '.join(endings)}")
    return "\n".join(lines) if lines else "(톤 프로필 비어있음)"


def _format_bl(bl: BlContext | None) -> str:
    if bl is None:
        return "(BL 정보 없음 — 시나리오 단독 트리거)"
    parts: list[str] = []
    if bl.bl_number:
        parts.append(f"- BL 번호: {bl.bl_number}")
    if bl.container_no:
        parts.append(f"- 컨테이너 번호: {bl.container_no}")
    if bl.product:
        parts.append(f"- 품목: {bl.product}")
    if bl.quantity is not None:
        parts.append(f"- 수량: {bl.quantity}개")
    if bl.departure_date:
        parts.append(f"- 출발일: {bl.departure_date.isoformat()}")
    if bl.arrival_date:
        parts.append(f"- 도착 예정일: {bl.arrival_date.isoformat()}")
    if bl.destination:
        parts.append(f"- 도착지: {bl.destination}")
    return "\n".join(parts) if parts else "(BL 컬럼 모두 비어있음)"


def _format_beats(beats: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for beat in beats:
        step = beat.get("step", "?")
        intent = beat.get("intent", "")
        tone = beat.get("tone_hint")
        line = f"{step}. {intent}"
        if tone:
            line += f"  (톤: {tone})"
        lines.append(line)
    return "\n".join(lines)


def _format_examples(examples: list[dict[str, Any]] | None) -> str:
    if not examples:
        return "(예시 없음)"
    lines: list[str] = []
    for ex in examples:
        sender = ex.get("sender", "?")
        content = ex.get("content", "")
        lines.append(f"  {sender}: {content}")
    return "\n".join(lines)


def build_prompt(
    *,
    scenario: ScenarioContext,
    sender: PersonaContext,
    receiver: PersonaContext,
    bl: BlContext | None,
    now: datetime | None = None,
    timing_profile: TimingProfile = "normal",
) -> ConversationPrompt:
    """시나리오/페르소나/BL 을 Claude 프롬프트 페이로드로 변환.

    system 프롬프트: 페르소나 역할 + 톤 + AI 티 제거 규칙 + 시간 분포 가이드 + 출력 스키마.
    user 메시지: BL + 시나리오 비트 + few-shot 예시 + 작성 지시.

    now: 시각대(KST) 인식용. None 이면 호출 시점 KST.
    timing_profile: short/normal/varied — 메시지 간격 분포 가이드 선택 (T9 — 2026-05-26).
    """
    if now is None:
        now = datetime.now(ZoneInfo("Asia/Seoul"))
    today_str = now.date().isoformat()
    now_str = now.strftime("%H:%M KST")

    system = f"""\
당신은 한국 무역회사 신사업유통 부서의 텔레그램 채팅 작성을 돕는 시스템입니다.

대화 참여자는 두 명입니다:
- 발신자: {sender.account_label} ({sender.display_name}, role={sender.role})
- 수신자: {receiver.account_label} ({receiver.display_name}, role={receiver.role})

[발신자 톤 프로필]
{_format_tone_profile(sender.tone_profile)}

[수신자 톤 프로필]
{_format_tone_profile(receiver.tone_profile)}

오늘 날짜: {today_str}
현재 시각: {now_str}

당신의 임무는 두 사람의 자연스러운 한국어 비즈니스 채팅을 작성하는 것입니다.

여러 주제가 한 대화에 포함될 수 있습니다 — 자연스럽게 화제 전환하되 모든 비트를 다루세요.

{ANTI_AI_RULES}

{timing_guide(timing_profile)}

{OUTPUT_SCHEMA_DOC}
"""

    user_content = f"""\
[시나리오]
이름: {scenario.name}
트리거: {scenario.trigger_event}

[BL 컨텍스트]
{_format_bl(bl)}

[대화 비트 — 이 흐름을 따라 작성]
{_format_beats(scenario.beats)}

[참고 예시 — 실제 대화 톤. 동일하게 따라 쓰지 말고, 어조만 학습할 것]
{_format_examples(scenario.example_msgs)}

위 정보를 바탕으로 두 사람의 자연스러운 한국어 채팅을 JSON 으로 작성하세요.
규칙을 어기면 안 됩니다. JSON 만 응답하고 다른 텍스트는 포함하지 마세요.
"""
    return ConversationPrompt(system=system, user_content=user_content)


def extract_messages_from_response(text: str) -> list[dict[str, Any]]:
    """Claude 응답 텍스트에서 JSON 메시지 리스트만 추출.

    Claude 가 ``` 펜스로 감싸거나 앞뒤에 텍스트를 붙이는 경우 대비.
    잘못된 JSON 이면 ``ValueError`` 발생 — 호출자가 재시도.
    """
    cleaned = text.strip()
    # ```json 펜스 제거
    if cleaned.startswith("```"):
        # 첫 줄과 마지막 줄 제거
        lines = cleaned.split("\n")
        lines = [ln for ln in lines if not ln.startswith("```")]
        cleaned = "\n".join(lines).strip()
    # JSON 객체만 추출 시도 (앞뒤 텍스트 있을 경우)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end < 0 or end < start:
        raise ValueError("Claude 응답에서 JSON 객체를 찾지 못함")
    payload = cleaned[start : end + 1]
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("Claude 응답이 JSON 객체가 아님")
    msgs = parsed.get("messages")
    if not isinstance(msgs, list):
        raise ValueError("응답에 messages 리스트가 없음")
    return msgs
