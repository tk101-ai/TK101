"""운영 요약의 서술 항목(홍보 방향·진행 이슈사항) AI 초안.

시트에 없는 전략 서술을 데이터(진행제품·플랫폼별 성과)에 근거해 **초안**으로
생성한다. 오너 결정: AI 초안 + 사람 검수. 따라서 초안은 검수 전제이며, 호출
실패/키 부재 시 빈 문자열로 폴백(라우터가 양식 기본 문구 유지).

운영 리뷰(S14 TO-BE)는 1차 범위 밖(수동 유지)이라 여기서 생성하지 않는다.
"""
from __future__ import annotations

import logging

from app.config import settings
from app.services.llm.client import call_claude

logger = logging.getLogger(__name__)

_SYSTEM = (
    "너는 동아제약 OTC 글로벌 SNS 마케팅 대행사의 운영보고서 작성자다. "
    "월간 운영 데이터를 바탕으로 보고서의 '홍보 방향'과 '진행 이슈사항' 항목 "
    "초안을 한국어로 작성한다.\n"
    "규칙:\n"
    "- 사실/수치는 제공된 데이터에서만 인용하고, 없는 수치를 지어내지 않는다.\n"
    "- 보고서 표 칸 크기가 제한적이다. **분량을 엄격히 지켜라.**\n"
    "- '홍보 방향': 2~3개 전략 방향을 번호로, 각 방향은 1줄로 간결히(실행 포인트 1개씩). "
    "**전체 400자 이내**, 불필요한 줄바꿈 금지.\n"
    "- '진행 이슈사항': 데이터상 핵심 이슈+대응책을 1개만, **80자 이내 한 문장**으로. "
    "명확한 이슈가 없으면 '특이 이슈 없음'.\n"
    "- 출력은 정확히 아래 JSON 형식만: "
    '{"홍보 방향": "...", "진행 이슈사항": "..."} (다른 텍스트 금지)'
)

# 칸 용량에 맞춘 하드 캡(LLM이 초과해도 안전하게 자른다).
_MAX_DIRECTION_CHARS = 600
_MAX_ISSUE_CHARS = 110


def draft_narrative(
    *,
    region_label: str,
    products: str,
    summary_text: str,
) -> dict:
    """지역(중화권/북미)의 홍보방향·진행이슈 초안 dict. 실패 시 빈 dict."""
    import json

    user = (
        f"[시장] {region_label}\n"
        f"[진행 제품] {products}\n"
        f"[이번 달 배포/성과 요약]\n{summary_text}\n\n"
        "위 데이터로 '홍보 방향'과 '진행 이슈사항' 초안을 JSON으로 작성하라."
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
        logger.warning("운영보고서 서술 초안 생성 실패(%s) — 빈 값 폴백", region_label, exc_info=True)
        return {}

    text = (resp.text or "").strip()
    # ```json 펜스 제거 후 파싱
    if text.startswith("```"):
        text = text.strip("`")
        text = text[text.find("{"): text.rfind("}") + 1] if "{" in text else text
    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        logger.warning("운영보고서 서술 초안 JSON 파싱 실패 — 빈 값 폴백")
        return {}
    caps = {"홍보 방향": _MAX_DIRECTION_CHARS, "진행 이슈사항": _MAX_ISSUE_CHARS}
    out = {}
    for k in ("홍보 방향", "진행 이슈사항"):
        v = data.get(k)
        if isinstance(v, str) and v.strip():
            text = v.strip()
            cap = caps[k]
            if len(text) > cap:  # 칸 넘침 방지(검수 전제이므로 잘라도 무방)
                text = text[: cap - 1].rstrip() + "…"
            # 검수 전제 표식(세로 공간 절약 위해 인라인).
            out[k] = f"[초안] {text}"
    return out
