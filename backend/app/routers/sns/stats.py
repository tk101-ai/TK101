"""SNS 통계 위젯 엔드포인트 — 집계는 services.sns_stats 가 담당(라우터는 얇다)."""

from fastapi import Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.sns import (
    GrowthCard,
    TopPost,
    TrendPoint,
    WeeklyKpiRow,
    WeeklyPostCountRow,
)
from app.services import sns_stats

from ._common import router

# ---------------- 통계 (위젯용) ----------------


@router.get("/stats/weekly", response_model=list[WeeklyKpiRow])
async def stats_weekly(
    year: int = Query(...),
    month: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """어권 × 플랫폼 × 주차 KPI 테이블.

    팔로워는 해당 주차 스냅샷에서, 게시물 카운트/조회수/반응수는 같은 (year, month, week_number)
    범위에 속하는 social_posts에서 ISO week로 GROUP BY해서 집계한다.
    """
    return await sns_stats.compute_weekly_kpi(db, year=year, month=month)


@router.get("/stats/weekly-posts", response_model=list[WeeklyPostCountRow])
async def stats_weekly_posts(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
):
    """계정(채널)별 주차별 게재건수 + 월 누적.

    주어진 (year, month)의 social_posts 를 계정 × 주차로 GROUP BY 한다.
    주차 = FLOOR((day-1)/7)+1 (week_of_month, 1~5) — stats_weekly 및
    sns_export._week_of_month 와 동일 공식(floor 월중 주차).
    각 계정 행은 week1~week5(주차별 건수) + total(월 합계)을 가진다.
    """
    return await sns_stats.compute_weekly_post_counts(db, year=year, month=month)


@router.get("/stats/growth", response_model=list[GrowthCard])
async def stats_growth(db: AsyncSession = Depends(get_db)):
    """채널별 최신 스냅샷 vs 직전 스냅샷 비교."""
    return await sns_stats.compute_growth_cards(db)


@router.get("/stats/top-posts", response_model=list[TopPost])
async def stats_top_posts(
    limit: int = Query(5, ge=1, le=50),
    language: str | None = Query(None),
    platform: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    return await sns_stats.compute_top_posts(
        db, limit=limit, language=language, platform=platform
    )


@router.get("/stats/trend", response_model=list[TrendPoint])
async def stats_trend(
    language: str | None = Query(None),
    platform: str | None = Query(None),
    account_id: str | None = Query(None),
    months: int = Query(6, ge=1, le=36, description="최근 N개월치 스냅샷만 조회"),
    db: AsyncSession = Depends(get_db),
):
    """채널별 팔로워 추이(시계열).

    `SocialWeeklySnapshot`을 (account × year × month × week) 단위로 조회해 차트용으로 반환한다.
    최근 `months`개월 범위만 포함하며, 오래된→최신 순으로 정렬한다. 프론트는 account별로
    시리즈를 묶거나 합산해 멀티라인 차트로 렌더한다.

    필터: `language`, `platform`, `account_id`. 미지정 시 전 채널.
    """
    return await sns_stats.compute_trend(
        db,
        language=language,
        platform=platform,
        account_id=account_id,
        months=months,
    )
