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
from app.services.llm.client import call_claude

logger = logging.getLogger(__name__)

DOC_TYPE_GUIDE: dict[str, str] = {
    "제안서": "회사소개·제안배경·세부 제안내용·기대효과·일정/견적 흐름의 비즈니스 제안서",
    "계획서": "목표·추진배경·세부 추진계획·일정·예산·기대효과 흐름의 사업/업무 계획서",
    "보고서": "개요·현황·분석·시사점·결론 흐름의 업무 보고서",
    "일반": "주제에 가장 적합한 논리적 구조의 한국어 비즈니스 문서",
}

# 문서 종류별 **고정 섹션 스켈레톤**(순서대로). 모델이 매 실행마다 제목/개수를 자유
# 선택하면 구조가 들쭉날쭉해지므로, 알려진 종류는 아래 소제목을 그 순서/문구 그대로
# 사용하게 강제한다. "일반"은 의도적으로 비워 모델이 주제에 맞게 자유 구성하게 둔다.
DOC_TYPE_SKELETON: dict[str, list[str]] = {
    "제안서": ["회사소개", "제안배경", "세부 제안내용", "기대효과", "일정/견적"],
    "계획서": ["목표", "추진배경", "세부 추진계획", "일정", "예산", "기대효과"],
    "보고서": ["개요", "현황", "분석", "시사점", "결론"],
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
    "- 굵게(**...**)로 핵심어를 강조해도 된다.\n"
    "\n[고품질 슬라이드 레이아웃 — 내용에 맞으면 적극 활용]\n"
    "단순 불릿보다 내용 성격에 맞는 레이아웃 블록을 쓰면 슬라이드가 훨씬 완성도 높게 "
    "디자인된다. 아래에 맞는 내용이면 ```layout``` 펜스로 넣는다(한 섹션에 0~2개, "
    "남용 금지 — 일반 설명·서술은 불릿/문단 그대로 둔다):\n"
    "- 핵심 수치·지표 2~4개 → kpi 카드:\n"
    "  ```layout\n"
    '  {"layout":"kpi","title":"핵심 지표","items":[{"value":"+42%","label":"매출 성장",'
    '"caption":"전년比"}]}\n'
    "  ```\n"
    "- 기존vs제안·옵션 등 2~3개 대조 → compare:\n"
    '  {"layout":"compare","title":"비교","columns":[{"heading":"기존","points":["항목1",'
    '"항목2"]},{"heading":"제안","points":["항목1","항목2"]}]}\n'
    "- 일정·로드맵·단계별 시점(2~5개) → timeline:\n"
    '  {"layout":"timeline","title":"로드맵","milestones":[{"label":"1단계","title":"착수",'
    '"detail":"세부"}]}\n'
    "- 절차·방법론 순서(2~6단계) → steps:\n"
    '  {"layout":"steps","title":"추진 절차","steps":[{"title":"현황 분석","detail":"세부"}]}\n'
    "- 핵심 메시지 한 줄 강조 → quote:\n"
    '  {"layout":"quote","text":"핵심 한 줄 메시지","attribution":"출처(선택)"}\n'
    "규칙: 각 레이아웃은 유효한 JSON 한 덩어리로 독립된 ```layout``` 펜스에 넣는다. "
    "kpi 수치도 참고자료 근거 없으면 지어내지 말 것(차트와 동일)."
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
    "- [필수 섹션 구성]이 주어지면 그 소제목들을 **순서·문구 그대로** sections 의 heading 으로 "
    "쓰고(추가/삭제/순서변경 금지) 각 본문을 채운다. 주어지지 않으면 4~8개 내외로 문서 "
    "종류에 맞게 자유 구성한다.\n\n"
    + _BODY_GUIDE
)


@dataclass(frozen=True)
class GeneratedDoc:
    title: str
    sections: list[dict]          # [{"heading","body"}]
    used_sources: list[str]
    cost_usd: float
    model: str
    # 잡 영속화(form_jobs)·관리자 토큰 집계용 — LLMResponse 에서 채운다(가산적).
    input_tokens: int = 0
    output_tokens: int = 0
    trace_id: str | None = None


def _build_user_prompt(topic: str, doc_type: str, chunks: list) -> str:
    guide = DOC_TYPE_GUIDE.get(doc_type, DOC_TYPE_GUIDE["일반"])
    if chunks:
        ctx = "\n\n".join(
            f"[참고자료 {i + 1}] 출처: {c.file_path}\n{(c.content or '')[:1200]}"
            for i, c in enumerate(chunks)
        )
    else:
        ctx = "(검색된 회사 자료 없음 — 일반적 구조로 작성하되 구체 수치는 만들지 말 것)"
    # 알려진 종류는 고정 스켈레톤 소제목을 그대로 쓰게 강제(구조 일관성↑). "일반"은 자유.
    skeleton = DOC_TYPE_SKELETON.get(doc_type)
    skeleton_block = ""
    if skeleton:
        headings = "\n".join(f"{i + 1}. {h}" for i, h in enumerate(skeleton))
        skeleton_block = (
            "\n[필수 섹션 구성] 아래 소제목을 이 순서·문구 그대로 sections 의 heading 으로 "
            "사용하고 각 본문을 [참고자료]에 근거해 채운다(소제목 추가/삭제/변경 금지):\n"
            f"{headings}\n"
        )
    return (
        f"문서 종류: {doc_type} ({guide})\n"
        f"작성 요구사항:\n{topic}\n"
        f"{skeleton_block}\n"
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
        max_tokens=16000,  # 4~8섹션 한국어 문서 — 8192는 자주 잘려 JSON 파싱 실패→502
        temperature=0.4,   # 일관성↑(과거 기본 1.0이라 실행마다 품질 편차 컸음)
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
        input_tokens=resp.input_tokens,
        output_tokens=resp.output_tokens,
        trace_id=resp.trace_id,
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
) -> tuple[dict, float, str, tuple[int, int]]:
    """문서의 한 섹션만 재생성. (section dict, cost_usd, model, (입력토큰, 출력토큰)) 반환."""
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
        temperature=0.4,  # 일관성↑
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
    return section, resp.cost_usd, resp.model, (resp.input_tokens, resp.output_tokens)


def _chart_to_note(match: re.Match) -> str:
    """차트 펜스 → 미리보기용 한 줄 표기(날 JSON 노출 방지)."""
    try:
        data = json.loads(match.group(1))
        title = str(data.get("title") or "데이터 차트")
    except (json.JSONDecodeError, ValueError, AttributeError):
        title = "데이터 차트"
    return f"> 📊 차트: {title}"


_CHART_FENCE = re.compile(r"```chart\s*(\{.*?\})\s*```", re.DOTALL)
_LAYOUT_FENCE = re.compile(r"```layout\s*(\{.*?\})\s*```", re.DOTALL)


def _layout_to_note(match: re.Match) -> str:
    """레이아웃 펜스 → 미리보기용 읽기 좋은 마크다운(날 JSON 노출 방지, 내용 보존).

    .pptx 는 디자인 슬라이드로 렌더하지만, 미리보기에서는 같은 정보를 평이한 목록으로
    보여줘 사용자가 내용을 확인/편집할 수 있게 한다.
    """
    try:
        d = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError, AttributeError):
        return "> 🧩 레이아웃 블록"
    kind = str(d.get("layout") or "")
    title = str(d.get("title") or "").strip()
    lines: list[str] = []
    if title:
        lines.append(f"**{title}**")
    if kind == "kpi":
        for it in d.get("items") or []:
            cap = f" ({it.get('caption')})" if it.get("caption") else ""
            lines.append(f"- {it.get('label', '')}: **{it.get('value', '')}**{cap}")
    elif kind == "compare":
        for col in d.get("columns") or []:
            lines.append(f"- **{col.get('heading', '')}**")
            lines += [f"  - {p}" for p in (col.get("points") or [])]
    elif kind == "timeline":
        for m in d.get("milestones") or []:
            label = f"[{m.get('label')}] " if m.get("label") else ""
            detail = f" — {m.get('detail')}" if m.get("detail") else ""
            lines.append(f"- {label}{m.get('title', '')}{detail}")
    elif kind == "steps":
        for i, st in enumerate(d.get("steps") or [], 1):
            detail = f" — {st.get('detail')}" if st.get("detail") else ""
            lines.append(f"{i}. {st.get('title', '')}{detail}")
    elif kind == "quote":
        lines.append(f"> {d.get('text', '')}")
        if d.get("attribution"):
            lines.append(f"> — {d['attribution']}")
    return "\n".join(lines) if lines else "> 🧩 레이아웃 블록"


def render_markdown(title: str, sections: list[dict]) -> str:
    """미리보기용 마크다운. 차트·레이아웃 펜스는 읽기 좋은 표기로 치환."""
    parts = [f"# {title}", ""]
    for s in sections:
        parts.append(f"## {s.get('heading', '')}")
        body = _CHART_FENCE.sub(_chart_to_note, s.get("body", ""))
        body = _LAYOUT_FENCE.sub(_layout_to_note, body)
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
    "※ 본문의 ```chart```/```layout``` 블록은 의도된 디자인 요소다(차트·KPI/비교/타임라인 "
    "등으로 렌더된다). JSON 문법 자체를 문제삼지 말고 내용으로 평가한다. 단 kpi/chart 의 "
    "수치에도 근거성 규칙을 동일하게 적용한다.\n"
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
) -> tuple[dict, float, str, tuple[int, int]]:
    """생성 초안을 LLM judge로 평가. (review dict, cost_usd, model, (입력토큰, 출력토큰)) 반환."""
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
        temperature=0,  # 평가(judge)는 결정적
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
    return review, resp.cost_usd, resp.model, (resp.input_tokens, resp.output_tokens)


def _problem_sections(review: dict, sections: list[dict]) -> list[int]:
    """검수 결과에서 재생성 대상 섹션 인덱스 목록(점수 낮은 순). grounded=false 또는
    issues 가 비어있지 않은 섹션만. review 의 heading 으로 sections 인덱스를 매칭한다."""
    by_heading: dict[str, int] = {}
    for i, s in enumerate(sections):
        h = str(s.get("heading") or "").strip()
        if h and h not in by_heading:
            by_heading[h] = i
    targets: list[tuple[int, int]] = []  # (issue 개수, 인덱스) — 문제 많은 순 정렬용
    for r in review.get("section_reviews") or []:
        h = str(r.get("heading") or "").strip()
        idx = by_heading.get(h)
        if idx is None:
            continue
        issues = r.get("issues") or []
        if (not r.get("grounded", True)) or issues:
            targets.append((len(issues), idx))
    # 문제(issue) 많은 섹션 우선, 동률이면 문서 순서. 인덱스 중복 제거.
    targets.sort(key=lambda t: (-t[0], t[1]))
    seen: set[int] = set()
    ordered: list[int] = []
    for _, idx in targets:
        if idx not in seen:
            seen.add(idx)
            ordered.append(idx)
    return ordered


def generate_document_reviewed(
    topic: str,
    doc_type: str,
    chunks: list,
    *,
    max_sections: int | None = None,
) -> GeneratedDoc:
    """초안 생성 → LLM judge 검수 → 문제 섹션(근거성 미달/issues)만 재생성하는 오케스트레이터.

    generate_document 의 상위 래퍼. 비용/토큰은 초안+검수+재생성 호출을 모두 가산한다.
    재생성 섹션 수는 max_sections(기본 settings.docgen_auto_review_max_sections)로 상한.
    검수/재생성 단계에서 예외가 나도 초안은 살린다(best-effort 품질 향상).
    """
    doc = generate_document(topic, doc_type, chunks)
    cap = max_sections if max_sections is not None else settings.docgen_auto_review_max_sections
    if cap <= 0 or not doc.sections:
        return doc

    cost = doc.cost_usd
    in_tok = doc.input_tokens
    out_tok = doc.output_tokens

    # 1) 검수(judge). 실패하면 초안 그대로 반환.
    try:
        review, r_cost, _model, (r_in, r_out) = review_document(
            topic, doc_type, doc.title, doc.sections, chunks
        )
    except Exception:  # noqa: BLE001 - 검수 실패가 초안 반환을 막아선 안 됨
        logger.warning("docgen 자동검수 실패 — 초안 그대로 반환", exc_info=True)
        return doc
    cost += r_cost
    in_tok += r_in
    out_tok += r_out

    # 2) 문제 섹션을 상한 개수만큼 재생성.
    targets = _problem_sections(review, doc.sections)[:cap]
    if not targets:
        logger.info("docgen 자동검수: 재생성 대상 없음(score=%s)", review.get("overall_score"))
        return doc

    reviews_by_heading = {
        str(r.get("heading") or "").strip(): r for r in (review.get("section_reviews") or [])
    }
    new_sections = list(doc.sections)  # 불변 패턴 — 원본 doc.sections 는 건드리지 않음
    regenerated: list[str] = []
    for idx in targets:
        sec = new_sections[idx]
        heading = sec.get("heading", "")
        r = reviews_by_heading.get(heading.strip(), {})
        # 검수가 짚은 issues + suggestions 를 재생성 피드백으로 전달.
        feedback_parts = [f"- {x}" for x in (r.get("issues") or [])]
        feedback_parts += [f"- (개선안) {x}" for x in (r.get("suggestions") or [])]
        feedback = "검수에서 지적된 문제를 해결해 다시 써줘:\n" + "\n".join(feedback_parts)
        try:
            section, s_cost, _m, (s_in, s_out) = regenerate_section(
                topic, doc_type, heading, sec.get("body", ""), feedback, chunks
            )
        except Exception:  # noqa: BLE001 - 한 섹션 재생성 실패가 전체를 막지 않음
            logger.warning("docgen 자동검수: '%s' 섹션 재생성 실패(원본 유지)", heading, exc_info=True)
            continue
        new_sections[idx] = section
        cost += s_cost
        in_tok += s_in
        out_tok += s_out
        regenerated.append(heading)

    logger.info(
        "docgen 자동검수 완료: score=%s, 재생성 %d/%d 섹션 %s",
        review.get("overall_score"),
        len(regenerated),
        len(doc.sections),
        regenerated,
    )

    # 불변 — 새 GeneratedDoc 로 반환(원본 doc 은 그대로). trace_id 는 초안 것을 유지.
    return GeneratedDoc(
        title=doc.title,
        sections=new_sections,
        used_sources=doc.used_sources,
        cost_usd=cost,
        model=doc.model,
        input_tokens=in_tok,
        output_tokens=out_tok,
        trace_id=doc.trace_id,
    )
