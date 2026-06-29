"""리터치 프롬프트 생성 — 생성 문서를 고품질 크리에이티브 브리프로 변환.

생성된 문서(title + sections, 본문엔 표/차트/layout JSON 블록 포함)와 브랜드
테마(컬러/폰트)를 입력으로, 다른 AI(Gemini·GPT·Gamma 등) 또는 우리 generator
가 세련되고 브랜드 일관된 결과물을 만들 수 있는 상세 프롬프트를 LLM 으로 생성.

generator.py 와 동일하게 ``call_claude`` + ``settings.docgen_model`` 사용.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.services.docgen.theme import get_theme
from app.services.llm.client import call_claude

logger = logging.getLogger(__name__)

# 섹션 본문이 과도하게 길면 토큰 폭증 방지를 위해 컷(데이터 명세는 앞쪽에 충분).
_MAX_BODY_CHARS = 2500


def _rgb_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = rgb
    return f"#{r:02X}{g:02X}{b:02X}"


_SYSTEM = (
    "너는 최고 수준의 프레젠테이션/문서 아트디렉터다. 주어진 비즈니스 문서를, "
    "다른 AI 도구가 '세련되고 브랜드 일관된' 결과물로 재현/재디자인할 수 있는 "
    "상세하고 실행가능한 프롬프트(크리에이티브 브리프)로 변환한다.\n\n"
    "반드시 한국어로, 아래 구조를 모두 채워 출력한다:\n"
    "1) 문서 개요 — 목적·문서유형·대상 독자·톤앤매너.\n"
    "2) 슬라이드/섹션 구성 — 섹션마다: 제목, 전달할 핵심 메시지 1~2줄, "
    "표시할 데이터 포인트(표·차트·핵심수치는 수치까지 명시), 권장 시각화 형태.\n"
    "3) 비주얼 디렉션 — 브랜드 컬러(주어진 HEX 사용), 타이포 위계, 레이아웃 "
    "원칙(여백·대비·강조), 적용할 레이아웃 유형(핵심지표 카드/비교/타임라인/"
    "단계/인용 등 내용에 맞게).\n"
    "4) 산출물 사양 — 포맷(예: 16:9 슬라이드), 분량(슬라이드 수 가이드), 제약.\n\n"
    "원문에 없는 사실·수치를 지어내지 말 것. 데이터는 문서에 있는 것만 사용한다. "
    "프롬프트는 그대로 복사해 붙여넣으면 바로 작동하도록 자기완결적으로 쓴다. "
    "메타설명·머리말 없이 프롬프트 본문만 출력한다."
)

# target 별 출력 어법 힌트 — 같은 구조, 표현만 도구에 맞춤.
_TARGET_HINT: dict[str, str] = {
    "general": (
        "이 프롬프트는 어떤 AI 디자인/슬라이드 도구에든 붙여넣을 수 있는 범용 "
        "형태로 작성한다(특정 도구 기능에 의존하지 않음)."
    ),
    "gamma": (
        "이 프롬프트는 Gamma(자동 슬라이드 생성)에 붙여넣는다. 슬라이드 단위로 "
        "'--- 슬라이드 N: 제목' 형태의 명확한 구획과 카드/컬럼 구성을 제안한다."
    ),
    "gpt": (
        "이 프롬프트는 ChatGPT 에 붙여넣는다. 역할 부여 + 단계적 지시 + 산출물 "
        "형식 지정을 명확히 한다."
    ),
    "gemini": (
        "이 프롬프트는 Gemini 에 붙여넣는다. 명료한 지시와 구조화된 출력 요구를 "
        "강조한다."
    ),
    "internal": (
        "이 프롬프트는 우리 사내 문서 생성기에 다시 먹이는 '디자인 지시문'이다. "
        "고품질 슬라이드 레이아웃 블록 어휘(kpi 핵심지표카드 / compare 비교 / "
        "timeline 타임라인 / steps 단계 / quote 인용)를 섹션 내용에 맞게 적극 "
        "지정하고, 표·차트로 풀 데이터를 구체적으로 지목한다."
    ),
}


def _render_document(title: str, sections: list[dict]) -> str:
    parts = [f"# 문서 제목: {title}", ""]
    for i, sec in enumerate(sections, 1):
        heading = str(sec.get("heading", "")).strip()
        body = str(sec.get("body", "")).strip()
        if len(body) > _MAX_BODY_CHARS:
            body = body[:_MAX_BODY_CHARS] + "\n…(이하 생략)"
        parts.append(f"## 섹션 {i}: {heading}")
        parts.append(body)
        parts.append("")
    return "\n".join(parts)


def build_retouch_prompt(
    *,
    title: str,
    sections: list[dict],
    doc_type: str,
    topic: str | None,
    target: str,
) -> tuple[str, str, float]:
    """리터치 프롬프트 1건 생성. (prompt_text, model, cost_usd) 반환."""
    theme = get_theme()
    primary = _rgb_hex(theme.primary)
    accent = _rgb_hex(theme.accent)
    hint = _TARGET_HINT.get(target, _TARGET_HINT["general"])
    doc_repr = _render_document(title, sections)

    user = (
        f"[대상 도구]\n{hint}\n\n"
        f"[문서 유형] {doc_type}\n"
        f"[작성 주제/요구] {topic or '(명시 없음)'}\n"
        f"[브랜드 컬러] 주색 {primary}, 강조색 {accent} "
        f"(본문 {theme.body_font}, 제목 {theme.heading_font}, 푸터 '{theme.footer_text}')\n\n"
        f"[원본 문서 내용]\n{doc_repr}\n\n"
        "위 문서를 재현/재디자인하기 위한 프롬프트를 작성하라."
    )

    resp = call_claude(
        system_prompt=_SYSTEM,
        messages=[{"role": "user", "content": user}],
        model=settings.docgen_model,
        max_tokens=4000,
        temperature=0.5,
        trace_name="docgen_retouch",
    )
    return resp.text.strip(), resp.model, resp.cost_usd
