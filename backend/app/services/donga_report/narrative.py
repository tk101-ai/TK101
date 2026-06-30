"""운영 요약의 서술 항목(홍보 방향·진행 이슈사항) AI 초안.

시트에 없는 전략 서술을 데이터(진행제품·플랫폼별 성과)에 근거해 **초안**으로
생성한다. 오너 결정: AI 초안 + 사람 검수.

기존 보고서 형식에 맞춰 **구조화**로 출력한다:
- 홍보 방향 = 2~3개 방향, 각 방향은 [제목(파란 굵게) + 상세 1~2줄]. (pptx_filler 가
  파란 굵은 제목 + 검정 '•' 상세로 렌더 — 기존 보고서와 동일한 모양)
- 진행 이슈사항 = 한 문장(짧은 칸).

호출 실패/키 부재 시 빈 dict 폴백(라우터가 양식 기본 유지). 운영 리뷰(S14)는
별도(후속).
"""
from __future__ import annotations

import json
import logging

from app.config import settings
from app.services.llm.client import call_claude

logger = logging.getLogger(__name__)

# 고객사 전달용 공통 톤 가드 — 모든 서술 프롬프트에 적용.
_TONE = (
    "★중요(톤): 이 보고서는 **고객사(동아제약)에 직접 전달**된다. 항상 긍정적·건설적·"
    "전문적으로 쓴다. 성과·강점·성장 포인트를 우선 부각하고, 부족하거나 아쉬운 부분은 "
    "'문제/한계/저조/부진/부정' 같은 직설적 표현 대신 '다음 달 강화 기회', '추가 성장 "
    "여지', '향후 보완 포인트'처럼 **완곡하고 발전 지향적으로** 표현한다. "
    "'0%·저조·미흡·실패' 같은 노골적 부정 표현과 질책성 문구는 쓰지 않는다.\n"
)

_SYSTEM = (
    "너는 동아제약 OTC 글로벌 SNS 마케팅 대행사의 운영보고서 작성자다. "
    "월간 운영 데이터를 바탕으로 보고서의 '홍보 방향'과 '진행 이슈사항' 초안을 "
    "한국어로 작성한다.\n"
    + _TONE
    + "규칙:\n"
    "- 사실/수치는 제공된 데이터에서만 인용하고, 없는 수치를 지어내지 않는다.\n"
    "- 기존 보고서 톤: 전문적이고 구체적인 마케팅 전략 서술.\n"
    "- '홍보 방향'은 진행 제품·타깃 시장에 맞춘 **2~3개 전략 방향**. 각 방향은 "
    "title(전략을 압축한 제목, 35자 내외)과 details(그 전략의 실행 포인트 1~2개, "
    "각 45~70자)로 구성.\n"
    "- '진행 이슈사항'은 다음 달 더 좋은 성과를 위한 **강화 포인트/제안**을 건설적으로 "
    "한 문장(80자 이내)으로(부정 표현 금지, 제안형). 특별한 사안이 없으면 '특이 이슈 없음'.\n"
    "- 출력은 정확히 아래 JSON 만(다른 텍스트 금지):\n"
    '{"directions":[{"title":"...","details":["...","..."]}],"issue":"..."}'
)

_MAX_DIRECTIONS = 3
_MAX_DETAILS = 2
_MAX_TITLE = 50
_MAX_DETAIL = 90
_MAX_ISSUE = 110


def _clip(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def draft_narrative(*, region_label: str, products: str, summary_text: str) -> dict:
    """지역의 홍보방향(구조화)·진행이슈 초안. 반환 {"directions":[{title,details}], "issue":str}.
    실패 시 빈 dict."""
    user = (
        f"[시장] {region_label}\n"
        f"[진행 제품] {products}\n"
        f"[이번 달 배포/성과 요약]\n{summary_text}\n\n"
        "위 데이터로 '홍보 방향'(2~3개 방향, 각 title+details)과 '진행 이슈사항'을 "
        "JSON으로 작성하라."
    )
    try:
        resp = call_claude(
            system_prompt=_SYSTEM,
            messages=[{"role": "user", "content": user}],
            model=settings.docgen_model or settings.form_filler_sonnet_model,
            max_tokens=1500,
            temperature=0.4,
            trace_name="donga_report_narrative",
        )
    except Exception:  # noqa: BLE001 — 초안 실패가 보고서 생성을 막지 않게.
        logger.warning("운영보고서 서술 초안 실패(%s) — 빈 값 폴백", region_label, exc_info=True)
        return {}

    text = (resp.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "{" in text:
            text = text[text.find("{"): text.rfind("}") + 1]
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        logger.warning("운영보고서 서술 초안 JSON 파싱 실패 — 빈 값 폴백")
        return {}

    directions = []
    for d in (data.get("directions") or [])[:_MAX_DIRECTIONS]:
        if not isinstance(d, dict):
            continue
        title = _clip(str(d.get("title", "")), _MAX_TITLE)
        if not title:
            continue
        details = [
            _clip(str(x), _MAX_DETAIL)
            for x in (d.get("details") or [])[:_MAX_DETAILS]
            if str(x).strip()
        ]
        directions.append({"title": title, "details": details})

    issue = _clip(str(data.get("issue", "")), _MAX_ISSUE)
    out: dict = {}
    if directions:
        out["directions"] = directions
    if issue:
        out["issue"] = issue
    return out


def _call_json(system: str, user: str, *, max_tokens: int = 1200) -> dict:
    """공통 LLM JSON 호출(실패/파싱오류 시 빈 dict)."""
    try:
        resp = call_claude(
            system_prompt=system,
            messages=[{"role": "user", "content": user}],
            model=settings.docgen_model or settings.form_filler_sonnet_model,
            max_tokens=max_tokens,
            temperature=0.4,
            trace_name="donga_report_ai",
        )
    except Exception:  # noqa: BLE001
        logger.warning("운영보고서 AI 호출 실패 — 빈 값", exc_info=True)
        return {}
    text = (resp.text or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if "{" in text:
            text = text[text.find("{"): text.rfind("}") + 1]
    try:
        return json.loads(text)
    except Exception:  # noqa: BLE001
        logger.warning("운영보고서 AI JSON 파싱 실패 — 빈 값")
        return {}


_TOP3_SYSTEM = (
    "너는 동아제약 OTC 글로벌 SNS 마케팅 운영보고서의 '우수 콘텐츠 분석' 작성자다.\n"
    + _TONE
    + "규칙:\n"
    "- 제공된 상위 게시물 데이터(계정·지표)에서만 사실을 인용한다.\n"
    "- insights: 이번 달 우수 콘텐츠의 공통 성공 요인/긍정 시사점 2개. 각 한 줄(70자 이내).\n"
    "- contents: 상위 게시물 각각의 '콘텐츠 내용'(무엇을 어떤 식으로 다뤘는지 추정) "
    "한 줄(45자 이내). 입력 게시물 수만큼 순서대로.\n"
    "- 출력은 JSON 만: {\"insights\":[\"...\",\"...\"],\"contents\":[\"...\"]}"
)


def draft_top3(*, region_label: str, top_briefs: list[str]) -> dict:
    """우수 콘텐츠 분석. {"insights":[str], "contents":[str]} 또는 {}."""
    if not top_briefs:
        return {}
    listing = "\n".join(f"{i}. {b}" for i, b in enumerate(top_briefs, 1))
    user = f"[시장] {region_label}\n[상위 게시물]\n{listing}\n\n위로 우수 콘텐츠 분석을 JSON으로."
    data = _call_json(_TOP3_SYSTEM, user, max_tokens=900)
    insights = [_clip(str(x), 90) for x in (data.get("insights") or []) if str(x).strip()][:3]
    contents = [_clip(str(x), 60) for x in (data.get("contents") or []) if str(x).strip()]
    out: dict = {}
    if insights:
        out["insights"] = insights
    if contents:
        out["contents"] = contents
    return out


_REVIEW_SYSTEM = (
    "너는 동아제약 OTC 글로벌 SNS 마케팅 월간 운영보고서의 '운영 리뷰(총평)'와 "
    "'운영 제안(AS-IS/TO-BE)' 작성자다.\n"
    + _TONE
    + "규칙:\n"
    "- 제공된 이번 달·전월 성과 데이터에서만 사실/수치를 인용한다(없는 수치 금지).\n"
    "- review: 중화권·북미 전체 운영 총평을 3~4문장(300자 이내). **성과·성장을 우선 "
    "부각**하고, 전월 대비 성장 포인트를 강조한다. 아쉬운 점은 완곡한 '추가 강화 여지'로.\n"
    "- as_is/to_be: 각 2~3개 항목. 항목은 title(30자 내외)+detail(한 줄 70자 내외). "
    "이 둘은 'AS-IS=문제, TO-BE=해결'이 **아니다**. 기존 보고서처럼 둘 다 **전략**이다.\n"
    "  · as_is = 이번 달 운영에서 **효과가 좋았던 전략·강점·성과 요인**(전부 긍정 서술).\n"
    "  · to_be = 그 성과를 이어 **다음 단계로 확장할 발전 전략**(제안형).\n"
    "  ⚠️ 두 영역 모두 **부정·부족 서술 절대 금지**. '저조·미흡·낮음·부족·한계·제한·"
    "부재·어렵다·문제' 같은 단어를 쓰지 말 것. 수치가 낮은 항목도 '추가 성장 기회'로 "
    "긍정·제안형으로만 표현한다. 작성 후 부정 단어가 있으면 긍정 표현으로 바꿔라.\n"
    "- 출력은 JSON 만: "
    '{"review":"...","as_is":[{"title":"...","detail":"..."}],"to_be":[{"title":"...","detail":"..."}]}'
)


def _items_td(raw) -> list:
    out = []
    for x in (raw or [])[:3]:
        if isinstance(x, dict):
            t = _clip(str(x.get("title", "")), 40)
            d = _clip(str(x.get("detail", "")), 90)
            if t or d:
                out.append({"title": t, "detail": d})
        elif str(x).strip():
            out.append({"title": "", "detail": _clip(str(x), 90)})
    return out


def draft_review(*, month: int, context: str) -> dict:
    """운영 리뷰 + AS-IS/TO-BE(제목+상세). {"review":str,"as_is":[{title,detail}],...} 또는 {}."""
    user = f"[{month}월 운영 데이터]\n{context}\n\n위로 운영 리뷰와 AS-IS/TO-BE를 JSON으로."
    data = _call_json(_REVIEW_SYSTEM, user, max_tokens=1500)
    review = _clip(str(data.get("review", "")), 380)
    as_is = _items_td(data.get("as_is"))
    to_be = _items_td(data.get("to_be"))
    out: dict = {}
    if review:
        out["review"] = review
    if as_is:
        out["as_is"] = as_is
    if to_be:
        out["to_be"] = to_be
    return out
