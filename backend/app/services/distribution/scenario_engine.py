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

# 대화 언어 (T9 — 2026-05-27). ko=한국어, zh=간체 중국어.
Language = Literal["ko", "zh"]

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


# 중국어(간체) 메시지 간격 가이드 — 한국어판과 동일한 분포 규칙을 중국어로 표현.
_TIMING_GUIDES_ZH: dict[str, str] = {
    "short": (
        "[消息间隔指南 — short / 快速来回]\n"
        "- 消息之间的间隔(send_after_sec)请控制在 30秒 ~ 30分钟 之间，节奏快。\n"
        "- 几乎是即时回复的聊天节奏。第一条 0秒，之后在 30~1800秒 范围内分布。\n"
        "- 同一个人连续拆分发送时，间隔大约 30秒~3分钟，成组发送。"
    ),
    "normal": (
        "[消息间隔指南 — normal / 日常业务]\n"
        "- 消息之间的间隔请在 5分钟 ~ 3小时(=180~10800秒) 之间自然混合。\n"
        "- 第一条 0秒，之后平均 20~40分钟，但要掺杂即时回复和 1~3小时 的延迟。\n"
        "- 间隔太均匀(比如全是5分钟、全是10分钟)很不自然 — 一定要拉开分布。"
    ),
    "varied": (
        "[消息间隔指南 — varied / 跨越一整天的节奏]\n"
        "- 刻意拉大间隔：1分钟 的秒回和 3~12小时(180~43200秒) 后才回的消息要混在一起。\n"
        "- 场景短一点也行，但要做出'上午搭话、下午/晚上才回'这样的节奏。\n"
        "- 发信方拆分信息连发时要短，对方的回复刻意留大间隔。\n"
        "- 至少要有一条消息的 send_after_sec 在 14400(4小时) 以上。"
    ),
}


def timing_guide(profile: TimingProfile, *, language: Language = "ko") -> str:
    """profile 에 해당하는 시간 분포 가이드 텍스트 반환 (언어별).

    language='zh' 면 중국어 가이드, 그 외/기본은 한국어 가이드.
    """
    guides = _TIMING_GUIDES_ZH if language == "zh" else _TIMING_GUIDES
    return guides.get(profile, guides["normal"])


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

# 중국어(간체) 출력 스키마 — 한국어판과 구조 동일, 안내문만 중국어.
OUTPUT_SCHEMA_DOC_ZH = """\
只返回 JSON 对象。不要添加任何其他文字或说明。

结构：
{
  "messages": [
    {
      "sender": "<account_label, 例: KR-A1>",
      "content": "<消息正文, 1~2句>",
      "send_after_sec": <距上一条消息发送后的秒数, 整数>,
      "typing_sec": <模拟打字的秒数, 整数, 通常 2~8>
    },
    ...
  ]
}

消息数量：5~14 条之间。
"""

# AI 티 제거 강제 규칙. 시나리오 무관 공통.
ANTI_AI_RULES = """\
다음 규칙을 절대 어기지 마세요:

[금지 표현]
- "도움이 되었으면 좋겠습니다", "확실히 알려드리겠습니다", "필요하시면 언제든"
- 너무 정확한 시간 표기 ("정확히 3시 47분에" 등)
- 영어 비즈니스 표현 직역 ("아래와 같이", "상기 내용", "본 건")
- 과도하게 정중한 문어체 ("~하셨음을 알려드립니다")

[스몰토크·안부 인사 절대 금지 — 업무 대화 전용]
- 이 대화는 100% 업무 대화입니다. 출고·재고·주문·정산·매입 등 비즈니스 주제에서 절대 벗어나지 마세요.
- "안녕하세요", "수고하세요", "잘 지내시죠", "오랜만이에요" 같은 안부 인사로 대화를 시작하지 마세요.
- 날씨·주말·식사·건강·가족·취미 같은 사적 잡담은 단 한 문장도 넣지 마세요.
- 첫 메시지는 인사·운(서두) 없이 곧바로 본론(시나리오 첫 비트의 핵심)으로 시작합니다.
- 비트에 없는 화제(사담)를 임의로 추가하지 마세요. 모든 메시지는 비트가 지시한 업무 내용만 다룹니다.
- 마무리 인사("감사합니다", "확인 부탁드려요" 등 업무 마무리 한두 마디)는 비트가 명시한 경우에만 짧게.

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

# AI 티 제거 강제 규칙 — 중국어(간체) 버전. 중국 현지인의 자연스러운 채팅 습관 반영.
# 한국어 어미·존댓말 흔적이 절대 섞이면 안 됨.
ANTI_AI_RULES_ZH = """\
请绝对不要违反以下规则：

[禁止表达]
- 不要用客服腔/AI腔: "希望对您有帮助"、"我一定为您查清楚"、"如有需要随时联系我"。
- 不要给出过于精确的时间("正好3点47分"之类)。
- 不要把英文商务措辞直译成生硬中文("如下所示"、"上述内容"、"本事项")。
- 不要用过度书面、过度客气的措辞("特此告知您已…")。
- 绝对不要出现任何韩语词尾或韩式敬语(例如 "~요"、"습니다"、"넵")。全程地道简体中文。

[绝对禁止寒暄·闲聊 — 纯业务对话]
- 这是 100% 的业务对话。只围绕发货、库存、订单、结算、采购等业务话题，绝不跑题。
- 不要用"你好""在吗""辛苦了""最近怎么样""好久不见"之类的寒暄开场。
- 绝对不要聊天气、周末、吃饭、健康、家人、爱好之类的私人闲扯，一句都不行。
- 第一条消息不带寒暄/铺垫，直接进入正题(场景第一个 beat 的核心)。
- 不要自行添加 beat 里没有的话题(闲谈)。每一条消息只谈 beat 指定的业务内容。
- 收尾客套("好的""麻烦您确认一下"之类业务收尾一两句)只在 beat 明确要求时才简短带上。

[商务礼貌语气 — 关键]
- 输出必须是自然、地道、有礼貌的商务中文(商务/礼貌语体, 带敬语感)，绝不能像生硬的逐字直译。
- 对对方适当用"您"(尤其是请求、确认、致谢、致歉时)；熟络的同事之间偶尔用"你"也自然，但请求/拜托时优先用"您"。
- 自然使用礼貌的商务表达: 麻烦您、请、收到了、好的、辛苦了、不好意思、麻烦了、谢谢您、这边、那边、您看一下。
- 用地道的中文连接词和口吻(那、那这样、这边、回头、稍等、行的话)，让句子顺畅自然。
- 语气要像真实贸易商之间客气往来 — 既不要机器翻译式的平铺直叙，也不要僵硬过度的官腔。保持口语化、客气、专业。
- 韩语原句仅作业务含义参考，绝不照搬韩语语序/词序；用中文母语者会怎么说来重写。

[必须表达]
- 一条消息只写 1~2 句。长了就拆开。
- 自然使用中文聊天里的语气词/口头禅: 好的、收到、明白、嗯、稍等、行、可以、那。
- 偶尔用口语缩略("这样的话"→"那"、"知道了"→"好的/行")。
- 约 3% 概率出现自然的轻微错别字(漏一个字或打错一个同音字)。
- 时间推进要自然 — 第一条之后 5分钟~数小时 的间隔混合。

[消息拆分模式]
- 发信方给多条信息时: 拆成几条短消息发，不一次性全发出来。
- 收信方通常回复更短更干脆。有时秒回，有时隔很久才回。

[语气一致性]
- 绝对不要违背各自的语气画像(tone profile)。
- 两个人的语气要有细微差别(一方更简短，一方更主导信息)。
"""


def anti_ai_rules(language: Language) -> str:
    """언어별 AI 티 제거 규칙 텍스트 반환."""
    return ANTI_AI_RULES_ZH if language == "zh" else ANTI_AI_RULES


def output_schema_doc(language: Language) -> str:
    """언어별 출력 스키마 안내문 반환."""
    return OUTPUT_SCHEMA_DOC_ZH if language == "zh" else OUTPUT_SCHEMA_DOC


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
    # 사용자 자유 텍스트 지시 (있으면 beats 대신/우선 흐름 가이드로 주입).
    instruction: str | None = None


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

    merged_instruction = "\n\n---\n\n".join(
        sc.instruction or "" for sc in scenarios if sc.instruction
    ) or None

    return ScenarioContext(
        name=name,
        trigger_event=scenarios[0].trigger_event,
        beats=merged_beats,
        example_msgs=merged_examples if merged_examples else None,
        raw_text=merged_raw,
        instruction=merged_instruction,
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


def _format_tone_profile(
    profile: dict[str, Any] | None, *, language: Language = "ko"
) -> str:
    """톤 프로필을 사람이 읽기 좋은 텍스트로 직렬화 (언어별 라벨).

    language='zh' 면 중국어 라벨 + 중국어 안내로 직렬화한다.
    common_phrases/preferred_endings 의 값 자체는 페르소나 데이터 그대로 노출하되,
    zh 일 때는 '中文里换成对应的口头禅/语气' 가이드를 덧붙여 LLM 이 맥락에 맞게 치환하도록 한다.
    """
    if language == "zh":
        return _format_tone_profile_zh(profile)
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


def _format_tone_profile_zh(profile: dict[str, Any] | None) -> str:
    """톤 프로필 중국어 직렬화 (간체)."""
    if not profile:
        return "(无特别语气要求 — 默认地道的中文商务聊天语气)"
    lines: list[str] = []
    if "formality" in profile:
        v = profile["formality"]
        lvl = "随和亲切" if v < 0.4 else "适中" if v < 0.7 else "正式客气"
        lines.append(f"- 正式程度: {lvl} ({v})")
    if "emoji_freq" in profile:
        lines.append(f"- 表情符号频率: {profile['emoji_freq']} (0=完全不用, 1=非常频繁)")
    if "typo_rate" in profile:
        lines.append(f"- 错别字比例: {profile['typo_rate']} (自然的、有意的轻微笔误)")
    if "common_phrases" in profile:
        phrases = profile["common_phrases"]
        if isinstance(phrases, list) and phrases:
            lines.append(
                f"- 常用语气(韩语参考，中文里请换成对应的口头禅/语气): {', '.join(phrases)}"
            )
    if "preferred_endings" in profile:
        endings = profile["preferred_endings"]
        if isinstance(endings, list) and endings:
            lines.append(
                f"- 偏好语尾(韩语参考，中文里用相应的语气词/收尾): {', '.join(endings)}"
            )
    return "\n".join(lines) if lines else "(语气画像为空)"


# BL 컨텍스트 라벨 — 언어별 (값은 데이터 그대로 노출).
_BL_LABELS: dict[Language, dict[str, str]] = {
    "ko": {
        "none": "(BL 정보 없음 — 시나리오 단독 트리거)",
        "empty": "(BL 컬럼 모두 비어있음)",
        "bl_number": "BL 번호",
        "container_no": "컨테이너 번호",
        "product": "품목",
        "quantity": "수량",
        "qty_unit": "개",
        "departure": "출발일",
        "arrival": "도착 예정일",
        "destination": "도착지",
    },
    "zh": {
        "none": "(无 BL 信息 — 场景单独触发)",
        "empty": "(BL 各列均为空)",
        "bl_number": "BL 单号",
        "container_no": "集装箱号",
        "product": "品类",
        "quantity": "数量",
        "qty_unit": "件",
        "departure": "出发日",
        "arrival": "预计到货日",
        "destination": "目的地",
    },
}


def _format_bl(bl: BlContext | None, *, language: Language = "ko") -> str:
    lbl = _BL_LABELS.get(language, _BL_LABELS["ko"])
    if bl is None:
        return lbl["none"]
    parts: list[str] = []
    if bl.bl_number:
        parts.append(f"- {lbl['bl_number']}: {bl.bl_number}")
    if bl.container_no:
        parts.append(f"- {lbl['container_no']}: {bl.container_no}")
    if bl.product:
        parts.append(f"- {lbl['product']}: {bl.product}")
    if bl.quantity is not None:
        parts.append(f"- {lbl['quantity']}: {bl.quantity}{lbl['qty_unit']}")
    if bl.departure_date:
        parts.append(f"- {lbl['departure']}: {bl.departure_date.isoformat()}")
    if bl.arrival_date:
        parts.append(f"- {lbl['arrival']}: {bl.arrival_date.isoformat()}")
    if bl.destination:
        parts.append(f"- {lbl['destination']}: {bl.destination}")
    return "\n".join(parts) if parts else lbl["empty"]


def _format_beats(beats: list[dict[str, Any]], *, language: Language = "ko") -> str:
    tone_label = "语气" if language == "zh" else "톤"
    lines: list[str] = []
    for beat in beats:
        step = beat.get("step", "?")
        intent = beat.get("intent", "")
        tone = beat.get("tone_hint")
        line = f"{step}. {intent}"
        if tone:
            line += f"  ({tone_label}: {tone})"
        lines.append(line)
    return "\n".join(lines)


def _format_examples(
    examples: list[dict[str, Any]] | None, *, language: Language = "ko"
) -> str:
    if not examples:
        return "(无示例)" if language == "zh" else "(예시 없음)"
    lines: list[str] = []
    for ex in examples:
        sender = ex.get("sender", "?")
        content = ex.get("content", "")
        lines.append(f"  {sender}: {content}")
    return "\n".join(lines)


def _format_instruction(instruction: str | None, *, language: Language = "ko") -> str:
    """사용자 자유 텍스트 지시를 프롬프트 블록으로 직렬화. 없으면 빈 문자열.

    고정 beats 대신/우선해서 LLM 에 흐름 가이드로 주입한다.
    """
    if not instruction or not instruction.strip():
        return ""
    if language == "zh":
        return (
            "\n[场景指示 — 按以下要求自由生成简短自然的对话, 不要照抄原文]\n"
            f"{instruction.strip()}\n"
        )
    return (
        "\n[지시 — 아래 요구에 맞춰 짧고 자연스러운 대화를 자유 생성. 원문을 그대로 베끼지 말 것]\n"
        f"{instruction.strip()}\n"
    )


def _build_system_prompt(
    *,
    scenario: ScenarioContext,
    sender: PersonaContext,
    receiver: PersonaContext,
    today_str: str,
    now_str: str,
    timing_profile: TimingProfile,
    language: Language,
) -> str:
    """언어별 system 프롬프트 구성 (역할 + 톤 + 규칙 + 시간 가이드 + 스키마)."""
    sender_tone = _format_tone_profile(sender.tone_profile, language=language)
    receiver_tone = _format_tone_profile(receiver.tone_profile, language=language)
    rules = anti_ai_rules(language)
    timing = timing_guide(timing_profile, language=language)
    schema = output_schema_doc(language)

    if language == "zh":
        return f"""\
你是协助一家韩国贸易公司"新事业流通"部门撰写 Telegram 聊天的系统。

对话参与者有两人：
- 发信方: {sender.account_label} ({sender.display_name}, role={sender.role})
- 收信方: {receiver.account_label} ({receiver.display_name}, role={receiver.role})

[发信方语气画像]
{sender_tone}

[收信方语气画像]
{receiver_tone}

今天日期: {today_str}
当前时间: {now_str}

你的任务是撰写这两人之间自然、地道、有礼貌的中文商务聊天(商务/礼貌语体, 带敬语感)。
要写成中文母语者真实往来的口吻 — 礼貌、口语、专业，绝不能是逐字直译的生硬中文。
适当用"您"、"麻烦您""请""收到了""好的""辛苦了""不好意思"等礼貌商务表达，但不要僵硬过度的官腔。

这是纯业务对话 — 只谈发货/库存/订单/结算/采购等正事，绝不寒暄或闲聊。

一段对话里可能包含多个话题 — 自然地切换话题，但要覆盖所有 beat。

{rules}

{timing}

{schema}
"""

    return f"""\
당신은 한국 무역회사 신사업유통 부서의 텔레그램 채팅 작성을 돕는 시스템입니다.

대화 참여자는 두 명입니다:
- 발신자: {sender.account_label} ({sender.display_name}, role={sender.role})
- 수신자: {receiver.account_label} ({receiver.display_name}, role={receiver.role})

[발신자 톤 프로필]
{sender_tone}

[수신자 톤 프로필]
{receiver_tone}

오늘 날짜: {today_str}
현재 시각: {now_str}

당신의 임무는 두 사람의 자연스러운 한국어 비즈니스 채팅을 작성하는 것입니다.

여러 주제가 한 대화에 포함될 수 있습니다 — 자연스럽게 화제 전환하되 모든 비트를 다루세요.

{rules}

{timing}

{schema}
"""


def _build_user_content(
    *,
    scenario: ScenarioContext,
    bl: BlContext | None,
    language: Language,
) -> str:
    """언어별 user 메시지 구성 (시나리오 + BL + 비트 + few-shot + 작성 지시)."""
    bl_text = _format_bl(bl, language=language)
    beats_text = _format_beats(scenario.beats, language=language)
    examples_text = _format_examples(scenario.example_msgs, language=language)
    instruction_block = _format_instruction(scenario.instruction, language=language)
    # 사용자 지시만 있고 고정 beats 가 비면 beat 자리에 자유 생성 안내.
    if not scenario.beats:
        beats_text = (
            "(无固定 beat — 参考[场景指示]自由生成简短自然的对话)"
            if language == "zh"
            else "(고정 비트 없음 — [지시]를 참고해 짧고 자연스럽게 자유 생성)"
        )

    if language == "zh":
        return f"""\
[场景]
名称: {scenario.name}
触发: {scenario.trigger_event}

[BL 上下文]
{bl_text}
{instruction_block}
[对话 beat — 按此流程撰写]
{beats_text}

[参考示例 — 真实对话语气。不要照抄，只学习语气]
{examples_text}

请基于以上信息，撰写这两人自然的中文聊天，并以 JSON 输出。
不得违反规则。只返回 JSON，不要包含任何其他文字。
"""

    return f"""\
[시나리오]
이름: {scenario.name}
트리거: {scenario.trigger_event}

[BL 컨텍스트]
{bl_text}
{instruction_block}
[대화 비트 — 이 흐름을 따라 작성]
{beats_text}

[참고 예시 — 실제 대화 톤. 동일하게 따라 쓰지 말고, 어조만 학습할 것]
{examples_text}

위 정보를 바탕으로 두 사람의 자연스러운 한국어 채팅을 JSON 으로 작성하세요.
규칙을 어기면 안 됩니다. JSON 만 응답하고 다른 텍스트는 포함하지 마세요.
"""


def build_prompt(
    *,
    scenario: ScenarioContext,
    sender: PersonaContext,
    receiver: PersonaContext,
    bl: BlContext | None,
    now: datetime | None = None,
    timing_profile: TimingProfile = "normal",
    language: Language = "ko",
) -> ConversationPrompt:
    """시나리오/페르소나/BL 을 Claude 프롬프트 페이로드로 변환.

    system 프롬프트: 페르소나 역할 + 톤 + AI 티 제거 규칙 + 시간 분포 가이드 + 출력 스키마.
    user 메시지: BL + 시나리오 비트 + few-shot 예시 + 작성 지시.

    now: 시각대(KST) 인식용. None 이면 호출 시점 KST.
    timing_profile: short/normal/varied — 메시지 간격 분포 가이드 선택 (T9 — 2026-05-26).
    language: ko(한국어, 기본) | zh(간체 중국어) — 모든 프롬프트 텍스트 분기 (T9 — 2026-05-27).
    """
    if now is None:
        now = datetime.now(ZoneInfo("Asia/Seoul"))
    today_str = now.date().isoformat()
    now_str = now.strftime("%H:%M KST")

    system = _build_system_prompt(
        scenario=scenario,
        sender=sender,
        receiver=receiver,
        today_str=today_str,
        now_str=now_str,
        timing_profile=timing_profile,
        language=language,
    )
    user_content = _build_user_content(
        scenario=scenario,
        bl=bl,
        language=language,
    )
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
