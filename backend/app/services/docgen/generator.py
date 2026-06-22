"""요구 기반 문서 초안 생성 — RAG 컨텍스트 + Claude로 구조화 문서 작성.

흐름: (라우터에서) nas_bridge.search_relevant_chunks 로 참고자료 검색 → generate_document
가 Claude에 [참고자료]와 요구를 주고 {title, sections[]} JSON을 받아 파싱한다.
환각 억제: 참고자료에 없는 구체 수치는 만들지 말도록 프롬프트로 강제.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from app.config import settings
from app.services.form_filler.llm_client import call_claude

logger = logging.getLogger(__name__)

DOC_TYPE_GUIDE: dict[str, str] = {
    "제안서": "회사소개·제안배경·세부 제안내용·기대효과·일정/견적 흐름의 비즈니스 제안서",
    "계획서": "목표·추진배경·세부 추진계획·일정·예산·기대효과 흐름의 사업/업무 계획서",
    "보고서": "개요·현황·분석·시사점·결론 흐름의 업무 보고서",
    "일반": "주제에 가장 적합한 논리적 구조의 한국어 비즈니스 문서",
}

# body 작성 가이드 — 슬라이드(PPT)와 워드 양쪽으로 디자인 렌더되므로, 평문 한 덩어리가
# 아니라 구조(불릿/표/차트)로 쓰게 유도한다. 렌더러(markdown_blocks)가 이 마크업을 해석한다.
_BODY_GUIDE = (
    "[body 작성 규칙 — 매우 중요]\n"
    "body 는 PPT 슬라이드와 워드 문서로 자동 디자인 렌더된다. 절대 긴 평문 한 덩어리로 "
    "쓰지 말고 아래 구조 요소를 적극 사용해 시각적으로 정리한다:\n"
    "- 핵심 항목은 '- ' 불릿으로 나눈다. 하위 항목은 2칸 들여써 중첩한다(- 상위\\n  - 하위).\n"
    "- 도입/맥락 1~2문장은 불릿 위 문단으로 둔다(슬라이드 1장 분량 ≈ 불릿 5~7개).\n"
    "- 비교·항목·일정·예산처럼 정형 데이터는 마크다운 표(| 항목 | 값 |)로 만든다.\n"
    "- 수치 추세/구성비/비교가 있으면 차트 블록을 넣는다(데이터가 참고자료에 있을 때만):\n"
    "  ```chart\n"
    '  {"type":"column","title":"제목","categories":["1Q","2Q","3Q"],'
    '"series":[{"name":"매출","values":[10,14,12]}]}\n'
    "  ```\n"
    "  type 은 column/bar/line/pie 중 하나. 지어낸 수치로 차트를 만들지 말 것.\n"
    "- 굵게(**...**)로 핵심어를 강조해도 된다."
)

_SYSTEM = (
    "당신은 TK101의 문서작성 보조 AI다. 제공된 [참고자료](회사 NAS 문서 검색결과)에 "
    "근거해 한국어 비즈니스 문서 초안을 작성한다.\n"
    "규칙:\n"
    "- 참고자료의 사실·수치·고유명사만 사실로 인용한다. 참고자료에 없는 구체 수치/실적은 "
    "지어내지 말고, 일반적 구조·문구나 '[확인 필요]' 플레이스홀더로 둔다.\n"
    "- 반드시 다음 JSON 스키마로만 응답한다(설명/코드펜스 없이 JSON만):\n"
    '{"title": "문서 제목", "sections": [{"heading": "소제목", "body": "구조화 한국어 본문"}], '
    '"used_sources": ["실제 인용한 참고자료의 출처 경로"]}\n'
    "- 섹션은 4~8개 내외로 문서 종류에 맞게 구성한다.\n\n"
    + _BODY_GUIDE
)


@dataclass(frozen=True)
class GeneratedDoc:
    title: str
    sections: list[dict]          # [{"heading","body"}]
    used_sources: list[str]
    cost_usd: float
    model: str


def _build_user_prompt(topic: str, doc_type: str, chunks: list) -> str:
    guide = DOC_TYPE_GUIDE.get(doc_type, DOC_TYPE_GUIDE["일반"])
    if chunks:
        ctx = "\n\n".join(
            f"[참고자료 {i + 1}] 출처: {c.file_path}\n{(c.content or '')[:1200]}"
            for i, c in enumerate(chunks)
        )
    else:
        ctx = "(검색된 회사 자료 없음 — 일반적 구조로 작성하되 구체 수치는 만들지 말 것)"
    return (
        f"문서 종류: {doc_type} ({guide})\n"
        f"작성 요구사항:\n{topic}\n\n"
        f"[참고자료]\n{ctx}"
    )


def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON 추출(코드펜스/잡설 방어)."""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.MULTILINE).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", t, flags=re.DOTALL)
        if m:
            return json.loads(m.group(0))
        raise


def generate_document(topic: str, doc_type: str, chunks: list) -> GeneratedDoc:
    """주제+참고자료 → 구조화 문서 초안. call_claude는 동기이므로 라우터에서 to_thread로 호출."""
    resp = call_claude(
        system_prompt=_SYSTEM,
        messages=[{"role": "user", "content": _build_user_prompt(topic, doc_type, chunks)}],
        model=settings.docgen_model,
        max_tokens=8192,
        cache_system=True,
        trace_name="docgen",
        trace_metadata={"doc_type": doc_type},
    )
    try:
        data = _parse_json(resp.text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.exception("docgen JSON 파싱 실패")
        raise ValueError(f"문서 생성 응답 파싱 실패: {exc}") from exc

    raw_sections = data.get("sections") or []
    sections = [
        {"heading": str(s.get("heading") or "").strip(), "body": str(s.get("body") or "").strip()}
        for s in raw_sections
        if isinstance(s, dict) and (s.get("heading") or s.get("body"))
    ]
    return GeneratedDoc(
        title=str(data.get("title") or topic[:60]).strip(),
        sections=sections,
        used_sources=[str(s) for s in (data.get("used_sources") or []) if s],
        cost_usd=resp.cost_usd,
        model=resp.model,
    )


_SECTION_SYSTEM = (
    "당신은 TK101의 문서작성 보조 AI다. 주어진 문서의 **한 섹션만** 다시 쓴다.\n"
    "규칙:\n"
    "- [참고자료]가 있으면 그 사실·수치·고유명사에 근거하고, 없는 구체 수치는 지어내지 마라.\n"
    "- 사용자 [수정 요청]이 있으면 그 의도를 최우선 반영한다.\n"
    "- 반드시 다음 JSON으로만 응답(코드펜스 없이): "
    '{"heading": "소제목", "body": "구조화 한국어 본문"}\n\n'
    + _BODY_GUIDE
)


def regenerate_section(
    topic: str,
    doc_type: str,
    heading: str,
    current_body: str,
    feedback: str,
    chunks: list,
) -> tuple[dict, float, str]:
    """문서의 한 섹션만 재생성. (section dict, cost_usd, model) 반환."""
    guide = DOC_TYPE_GUIDE.get(doc_type, DOC_TYPE_GUIDE["일반"])
    if chunks:
        ctx = "\n\n".join(
            f"[참고자료 {i + 1}] 출처: {c.file_path}\n{(c.content or '')[:1200]}"
            for i, c in enumerate(chunks)
        )
    else:
        ctx = "(검색된 회사 자료 없음 — 일반 구조로 작성하되 구체 수치는 만들지 말 것)"
    user = (
        f"문서 종류: {doc_type} ({guide})\n"
        f"문서 전체 주제: {topic}\n\n"
        f"다시 쓸 섹션 제목: {heading}\n"
        f"현재 본문:\n{current_body or '(비어 있음)'}\n\n"
        f"[수정 요청]\n{feedback or '(특별한 요청 없음 — 더 구체적이고 완성도 높게 다시 써줘)'}\n\n"
        f"[참고자료]\n{ctx}"
    )
    resp = call_claude(
        system_prompt=_SECTION_SYSTEM,
        messages=[{"role": "user", "content": user}],
        model=settings.docgen_model,
        max_tokens=4096,
        cache_system=True,
        trace_name="docgen.regenerate_section",
        trace_metadata={"doc_type": doc_type, "heading": heading},
    )
    try:
        data = _parse_json(resp.text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.exception("섹션 재생성 JSON 파싱 실패")
        raise ValueError(f"섹션 재생성 응답 파싱 실패: {exc}") from exc
    section = {
        "heading": str(data.get("heading") or heading).strip(),
        "body": str(data.get("body") or "").strip(),
    }
    return section, resp.cost_usd, resp.model


def _chart_to_note(match: re.Match) -> str:
    """차트 펜스 → 미리보기용 한 줄 표기(날 JSON 노출 방지)."""
    try:
        data = json.loads(match.group(1))
        title = str(data.get("title") or "데이터 차트")
    except (json.JSONDecodeError, ValueError, AttributeError):
        title = "데이터 차트"
    return f"> 📊 차트: {title}"


_CHART_FENCE = re.compile(r"```chart\s*(\{.*?\})\s*```", re.DOTALL)


def render_markdown(title: str, sections: list[dict]) -> str:
    """미리보기용 마크다운. 차트 펜스는 친화적 표기로 치환."""
    parts = [f"# {title}", ""]
    for s in sections:
        parts.append(f"## {s.get('heading', '')}")
        body = _CHART_FENCE.sub(_chart_to_note, s.get("body", ""))
        parts.append(body)
        parts.append("")
    return "\n".join(parts).strip()


_JUDGE_SYSTEM = (
    "당신은 TK101의 문서 품질 검수관(LLM-as-judge)이다. 작성된 비즈니스 문서 초안을 "
    "엄정하게 평가한다. 칭찬보다 문제 발견에 집중한다.\n"
    "평가 관점:\n"
    "1) 근거성(grounded): 본문의 구체 수치·실적·고유명사가 [참고자료]에 실제로 있는가. "
    "참고자료에 없는데 단정한 수치/실적은 환각으로 보고 grounded=false + issues에 명시.\n"
    "2) 요구 충족·누락: 작성 요구사항 대비 빠진 항목.\n"
    "3) 구조·완성도: 논리 흐름, 빈약/중복 섹션.\n"
    "반드시 다음 JSON으로만 응답(코드펜스 없이):\n"
    '{"overall_score": 0~100 정수, "summary": "총평 2~4문장", '
    '"section_reviews": [{"heading": "섹션제목", "grounded": true/false, '
    '"issues": ["문제점"], "suggestions": ["개선 제안"]}], '
    '"missing": ["요구 대비 누락/보강 필요 항목"]}'
)


def review_document(
    topic: str,
    doc_type: str,
    title: str,
    sections: list[dict],
    chunks: list,
) -> tuple[dict, float, str]:
    """생성 초안을 LLM judge로 평가. (review dict, cost_usd, model) 반환."""
    if chunks:
        ctx = "\n\n".join(
            f"[참고자료 {i + 1}] 출처: {c.file_path}\n{(c.content or '')[:1200]}"
            for i, c in enumerate(chunks)
        )
    else:
        ctx = "(참고자료 없음 — 근거성은 '확인 불가'로 보고 일반 품질만 평가)"
    body = "\n\n".join(
        f"## {s.get('heading', '')}\n{s.get('body', '')}" for s in sections
    )
    user = (
        f"문서 종류: {doc_type}\n작성 요구사항:\n{topic}\n\n"
        f"[검수 대상 초안] 제목: {title}\n{body}\n\n[참고자료]\n{ctx}"
    )
    resp = call_claude(
        system_prompt=_JUDGE_SYSTEM,
        messages=[{"role": "user", "content": user}],
        max_tokens=4096,
        cache_system=True,
        trace_name="docgen.review",
        trace_metadata={"doc_type": doc_type},
    )
    try:
        data = _parse_json(resp.text)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.exception("문서 검수 JSON 파싱 실패")
        raise ValueError(f"문서 검수 응답 파싱 실패: {exc}") from exc
    reviews = [
        {
            "heading": str(r.get("heading") or "").strip(),
            "grounded": bool(r.get("grounded", True)),
            "issues": [str(x) for x in (r.get("issues") or []) if x],
            "suggestions": [str(x) for x in (r.get("suggestions") or []) if x],
        }
        for r in (data.get("section_reviews") or [])
        if isinstance(r, dict)
    ]
    try:
        score = max(0, min(100, int(data.get("overall_score", 0))))
    except (ValueError, TypeError):
        score = 0
    review = {
        "overall_score": score,
        "summary": str(data.get("summary") or "").strip(),
        "section_reviews": reviews,
        "missing": [str(x) for x in (data.get("missing") or []) if x],
    }
    return review, resp.cost_usd, resp.model
