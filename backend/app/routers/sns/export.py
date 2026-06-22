"""SNS 엑셀 내보내기 (읽기전용 다운로드).

데이터 집계는 services.sns_stats, 워크북 빌드는 services.sns_export 가 담당.
라우터는 파일명/HTTP 경계(404 등)만 처리한다.
"""

from datetime import date

from fastapi import Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services import sns_stats
from app.services.sns_export import (
    build_content_status_workbook,
    build_full_brand_workbook,
    build_posts_workbook,
    build_snapshots_workbook,
)

from ._common import router, xlsx_response

# ---------------- 엑셀 내보내기 (읽기전용 다운로드) ----------------


@router.get("/export/content-status")
async def export_content_status(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """콘텐츠 현황(계정별 주차별 게재건수 + 합계) → .xlsx.

    페이지와 동일한 stats_weekly_posts 집계를 재사용한다. 계정 식별 컬럼
    (브랜드/플랫폼/어권/핸들)을 포함하며 특정 발주처를 하드코딩하지 않는다.
    """
    rows = await sns_stats.compute_weekly_post_counts(db, year=year, month=month)
    buf = build_content_status_workbook(rows)
    return xlsx_response(buf, f"콘텐츠현황_{year}-{month:02d}.xlsx")


@router.get("/export/snapshots")
async def export_snapshots(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """주간 팔로워(계정별 1~5주차) → .xlsx.

    snapshots 쿼리(social_weekly_snapshots × social_accounts)를 재사용해
    계정별로 주차 팔로워 수를 피벗한다. 계정이 추가되면 자동 반영된다.
    """
    rows = await sns_stats.collect_snapshots_export_rows(db, year=year, month=month)
    buf = build_snapshots_workbook(rows)
    return xlsx_response(buf, f"주간팔로워_{year}-{month:02d}.xlsx")


@router.get("/export/posts")
async def export_posts(
    account_id: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """게시물 목록 → .xlsx. account_id 생략 시 기간 내 모든 계정 게시물.

    list_posts 와 동일한 필터(account_id/date_from/date_to)를 쓰되, 계정 식별
    컬럼(브랜드/플랫폼/어권/핸들)을 위해 social_accounts 를 JOIN 한다.
    """
    rows = await sns_stats.collect_posts_export_rows(
        db, account_id=account_id, date_from=date_from, date_to=date_to
    )

    if date_from and date_to:
        period = f"{date_from.isoformat()}_{date_to.isoformat()}"
    elif date_from:
        period = f"{date_from.isoformat()}_이후"
    elif date_to:
        period = f"~{date_to.isoformat()}"
    else:
        period = "전체"
    buf = build_posts_workbook(rows)
    return xlsx_response(buf, f"게시물_{period}.xlsx")


@router.get("/export/workbook")
async def export_workbook(
    client: str = Query(..., description="브랜드(발주처). social_accounts.client 와 일치하는 채널만."),
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """브랜드별 통합 워크북 → .xlsx (월간요약 + 채널별 콘텐츠 + 팔로워).

    팀의 기존 구글시트 구조를 재현하며 marketing1 importer 와 라운드트립 호환된다.
    완전 동적 — 주어진 client 의 계정을 DB 에서 순회하므로 서울시/신세계 등 어떤
    브랜드도 자기 워크북을 자동 생성한다(특정 발주처/채널 하드코딩 없음).
    """
    (
        accounts,
        summary_rows,
        posts_by_account,
        snapshots_by_account,
    ) = await sns_stats.collect_brand_workbook_data(
        db, client=client, year=year, month=month
    )
    if not accounts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"브랜드 '{client}' 의 계정이 없습니다",
        )

    buf = build_full_brand_workbook(
        client=client,
        year=year,
        month=month,
        accounts=accounts,
        summary_rows=summary_rows,
        posts_by_account=posts_by_account,
        snapshots_by_account=snapshots_by_account,
    )
    safe_client = client or "전체"
    return xlsx_response(buf, f"{safe_client}_SNS_DB_{year}-{month:02d}.xlsx")
