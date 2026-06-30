"""동아제약 운영보고서 생성 오케스트레이션.

라이브 구글시트(관리문서) → 파싱 → 월 필터/선별 → 표·요약 빌드 → (선택)AI 초안
→ 양식 PPTX 채움 → bytes. 라우터가 이 함수를 호출해 다운로드로 내려준다.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.config import settings

from . import report_builder as rb
from .gsheets import fetch_tab
from .narrative import draft_narrative, draft_review, draft_top3
from .pptx_filler import fill_report
from .sheet_parser import SHEET_CHINA, SHEET_NA, parse_china, parse_na, pick_month

logger = logging.getLogger(__name__)


def _load_template() -> bytes:
    path = Path(settings.donga_report_template_path)
    if not path.is_file():
        raise RuntimeError(
            f"운영보고서 양식 파일을 찾을 수 없습니다: {path} "
            "(서버 경로에 양식 .pptx 를 두세요)"
        )
    return path.read_bytes()


async def generate_report(
    *,
    month: int,
    year: int = 2026,
    basis_date: str | None = None,
    include_narrative: bool = True,
) -> tuple[bytes, dict]:
    """운영보고서 PPTX bytes + 메타(건수 등) 생성.

    Returns (pptx_bytes, meta). 데이터/양식 문제는 RuntimeError 로 올린다.
    """
    sheet_id = settings.donga_sheet_id
    ch_rows, na_rows = await asyncio.gather(
        fetch_tab(sheet_id, SHEET_CHINA),
        fetch_tab(sheet_id, SHEET_NA),
    )
    all_ch = parse_china(ch_rows)
    all_na = parse_na(na_rows)
    ch_secs = pick_month(all_ch, month, year)
    na_secs = pick_month(all_na, month, year)
    ch = rb.distributed(rb.flatten(ch_secs))
    na = rb.distributed(rb.flatten(na_secs))
    if not ch and not na:
        raise RuntimeError(
            f"{year}년 {month}월 배포완료 데이터가 시트에 없습니다 "
            "(월 섹션/포스팅 일자 확인)"
        )

    china_sum = rb.china_summary(ch, ch_secs)
    na_sum = rb.na_summary(na, na_secs)
    # 전월 대비 추세(운영 리뷰 AI 근거)
    prev_ch = rb.distributed(rb.flatten(pick_month(all_ch, month - 1, year)))
    prev_na = rb.distributed(rb.flatten(pick_month(all_na, month - 1, year)))

    china_narr = na_narr = china_t3 = na_t3 = review = None
    if include_narrative:
        ch_briefs = [rb.post_brief(r) for r in rb.top_posts(ch, 3)]
        na_briefs = [rb.post_brief(r) for r in rb.top_posts(na, 3)]
        review_ctx = (
            f"[중화권] {china_sum['진행 제품']}; {china_sum['배포 수량']} "
            f"{china_sum['배포 데이터']}\n"
            f"[북미] {na_sum['진행 제품']}; {na_sum['배포 수량']} {na_sum['배포 데이터']}\n"
            f"[전월 대비 인터랙션] 중화권 {rb.total_interactions(prev_ch):,} → "
            f"{rb.total_interactions(ch):,}; 북미 {rb.total_interactions(prev_na):,} → "
            f"{rb.total_interactions(na):,}"
        )
        # AI 초안(블로킹 LLM)은 스레드로 병렬. 실패해도 폴백(빈 dict).
        china_narr, na_narr, china_t3, na_t3, review = await asyncio.gather(
            asyncio.to_thread(
                draft_narrative,
                region_label="중화권(중국 OTA: 마펑워·씨트립·따종디엔핑)",
                products=china_sum["진행 제품"],
                summary_text=f"{china_sum['배포 수량']}\n{china_sum['배포 데이터']}",
            ),
            asyncio.to_thread(
                draft_narrative,
                region_label="북미(인스타그램·틱톡)",
                products=na_sum["진행 제품"],
                summary_text=f"{na_sum['배포 수량']}\n{na_sum['배포 데이터']}",
            ),
            asyncio.to_thread(draft_top3, region_label="중화권", top_briefs=ch_briefs),
            asyncio.to_thread(draft_top3, region_label="북미", top_briefs=na_briefs),
            asyncio.to_thread(draft_review, month=month, context=review_ctx),
        )
        # 우수 콘텐츠 슬라이드 채움용 페이로드(4필드 박스 + 통계/인사이트)
        china_t3 = rb.top3_payload(ch, (china_t3 or {}).get("contents", []), (china_t3 or {}).get("insights", []))
        na_t3 = rb.top3_payload(na, (na_t3 or {}).get("contents", []), (na_t3 or {}).get("insights", []))

    pptx = fill_report(
        template_bytes=_load_template(),
        month=month,
        china_records=ch,
        na_records=na,
        china_summary_vals=china_sum,
        na_summary_vals=na_sum,
        china_narrative=china_narr,
        na_narrative=na_narr,
        china_top3=china_t3,
        na_top3=na_t3,
        review=review,
        china_comments=rb.total_comments(ch),
        na_comments=rb.total_comments(na),
        basis_date=basis_date,
    )
    meta = {
        "month": month,
        "year": year,
        "china_count": len(ch),
        "na_count": len(na),
        "narrative": bool(china_narr or na_narr),
        "review": bool(review),
        "top3": bool(china_t3 or na_t3),
    }
    logger.info("동아 운영보고서 생성: %s", meta)
    return pptx, meta
