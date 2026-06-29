"""HTML 디자인 덱 생성 — LLM이 디자인 프롬프트대로 자체완결 HTML 슬라이드 덱 작성.

python-pptx 고정 렌더러로는 임의 디자인 시스템(색/폰트/레이아웃/마스트헤드)을
반영할 수 없다. 대안: LLM이 주어진 디자인 시스템(사용자 프롬프트)을 그대로
HTML/CSS 로 구현한 16:9 덱을 만들고, 사용자는 브라우저에서 보거나 인쇄→PDF.

generator.py 와 동일하게 call_claude + settings.docgen_model 사용.
"""
from __future__ import annotations

import logging
import re

from app.config import settings
from app.services.llm.client import call_claude

logger = logging.getLogger(__name__)

# 섹션 본문이 매우 길면 토큰 폭증 방지(앞부분에 데이터 충분).
_MAX_BODY_CHARS = 3000

_SYSTEM = (
    "너는 최고 수준의 프레젠테이션 디자이너이자 프런트엔드 엔지니어다. "
    "주어진 [디자인 시스템]을 '있는 그대로' 구현한 자체완결 HTML 슬라이드 덱을 만든다.\n\n"
    "[출력 규칙 — 엄수]\n"
    "- 오직 완전한 HTML 문서 하나만 출력한다. 마크다운 코드펜스(```), 설명, 머리말 금지.\n"
    "- 모든 CSS는 <style> 에 인라인. 외부 의존은 폰트 CDN(link)만 허용.\n"
    "- 16:9 비율. 각 슬라이드는 1280×720(또는 1920×1080) 고정 캔버스 .slide 섹션.\n"
    "- [디자인 시스템]의 색(HEX)·폰트·타이포·레이아웃·마스트헤드·여백·밀도 규칙을 "
    "정확히 따른다. 색/폰트를 임의로 바꾸지 않는다.\n"
    "- 폰트가 지정되면 CDN으로 로드한다(예: Pretendard → "
    "https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css).\n"
    "- [콘텐츠]의 사실·수치·고유명사만 사용한다. 없는 수치를 지어내지 않는다. "
    "콘텐츠를 디자인 시스템에 맞춰 슬라이드로 배치한다(표지→본문 슬라이드들→마무리).\n"
    "- 인쇄 시 슬라이드 1장=PDF 1쪽이 되도록 print CSS 를 포함한다:\n"
    "  @media print { .slide { page-break-after: always; } }\n"
    "  @page { size: 1280px 720px; margin: 0; }\n"
    "- 화면에서는 슬라이드를 세로로 쌓아 스크롤로 모두 보이게 한다.\n"
    "- 빈 하단을 남기지 말고 [디자인 시스템]의 밀도 규칙대로 채운다."
)


def _render_content(title: str, sections: list[dict]) -> str:
    parts = [f"문서 제목: {title}", ""]
    for i, sec in enumerate(sections, 1):
        heading = str(sec.get("heading", "")).strip()
        body = str(sec.get("body", "")).strip()
        if len(body) > _MAX_BODY_CHARS:
            body = body[:_MAX_BODY_CHARS] + "\n…(생략)"
        parts.append(f"## {i}. {heading}")
        parts.append(body)
        parts.append("")
    return "\n".join(parts)


def _strip_fences(text: str) -> str:
    """혹시 코드펜스로 감싸 나오면 제거하고 <!doctype>/<html> 부터 취한다."""
    t = text.strip()
    t = re.sub(r"^```(?:html)?\s*|\s*```$", "", t, flags=re.MULTILINE).strip()
    m = re.search(r"(<!doctype html|<html)", t, flags=re.IGNORECASE)
    if m:
        t = t[m.start() :]
    return t


def generate_html_deck(
    *,
    title: str,
    sections: list[dict],
    doc_type: str,
    design_prompt: str,
    model: str | None = None,
) -> tuple[str, str, float]:
    """디자인 프롬프트 + 콘텐츠 → 자체완결 HTML 덱. (html, model, cost_usd) 반환."""
    content = _render_content(title, sections)
    user = (
        f"[문서 유형] {doc_type}\n\n"
        f"[디자인 시스템 — 이 스펙을 정확히 구현하라]\n{design_prompt.strip()}\n\n"
        f"[콘텐츠 — 이 내용으로 슬라이드를 채워라]\n{content}\n\n"
        "위 디자인 시스템을 그대로 적용한 완전한 HTML 슬라이드 덱을 출력하라."
    )
    resp = call_claude(
        system_prompt=_SYSTEM,
        messages=[{"role": "user", "content": user}],
        # 16000: docgen 생성과 동일(비스트리밍 허용 한도 내). 6~8슬라이드 덱에 충분.
        model=model or settings.docgen_model,
        max_tokens=16000,
        temperature=0.4,
        trace_name="docgen_html_deck",
        trace_metadata={"doc_type": doc_type},
    )
    return _strip_fences(resp.text), resp.model, resp.cost_usd
