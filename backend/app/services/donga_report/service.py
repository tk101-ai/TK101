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
from .narrative import draft_narrative
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
    ch_secs = pick_month(parse_china(ch_rows), month, year)
    na_secs = pick_month(parse_na(na_rows), month, year)
    ch = rb.distributed(rb.flatten(ch_secs))
    na = rb.distributed(rb.flatten(na_secs))
    if not ch and not na:
        raise RuntimeError(
            f"{year}년 {month}월 배포완료 데이터가 시트에 없습니다 "
            "(월 섹션/포스팅 일자 확인)"
        )

    china_sum = rb.china_summary(ch, ch_secs)
    na_sum = rb.na_summary(na, na_secs)

    china_narr = na_narr = None
    if include_narrative:
        # AI 초안은 블로킹 LLM 호출 → 스레드로(검수 전제, 실패해도 폴백).
        china_narr, na_narr = await asyncio.gather(
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
        )

    pptx = fill_report(
        template_bytes=_load_template(),
        month=month,
        china_records=ch,
        na_records=na,
        china_summary_vals=china_sum,
        na_summary_vals=na_sum,
        china_narrative=china_narr,
        na_narrative=na_narr,
        basis_date=basis_date,
    )
    meta = {
        "month": month,
        "year": year,
        "china_count": len(ch),
        "na_count": len(na),
        "narrative": bool(china_narr or na_narr),
    }
    logger.info("동아 운영보고서 생성: %s", meta)
    return pptx, meta
