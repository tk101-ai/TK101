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

_SYSTEM = (
    "너는 동아제약 OTC 글로벌 SNS 마케팅 대행사의 운영보고서 작성자다. "
    "월간 운영 데이터를 바탕으로 보고서의 '홍보 방향'과 '진행 이슈사항' 초안을 "
    "한국어로 작성한다.\n"
    "규칙:\n"
    "- 사실/수치는 제공된 데이터에서만 인용하고, 없는 수치를 지어내지 않는다.\n"
    "- 기존 보고서 톤: 전문적이고 구체적인 마케팅 전략 서술.\n"
    "- '홍보 방향'은 진행 제품·타깃 시장에 맞춘 **2~3개 전략 방향**. 각 방향은 "
    "title(전략을 압축한 제목, 35자 내외)과 details(그 전략의 실행 포인트 1~2개, "
    "각 45~70자)로 구성.\n"
    "- '진행 이슈사항'은 데이터상 핵심 이슈+대응책을 **한 문장(80자 이내)**으로. "
    "명확한 이슈가 없으면 '특이 이슈 없음'.\n"
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
