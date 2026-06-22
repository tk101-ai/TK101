"""SNS 내부(시스템) 라우터 — n8n cron 등이 X-Internal-Token 으로 호출.

수집 코어는 services.sns_collection 를 재사용한다.
"""

from fastapi import Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.sns import SocialAccount
from app.schemas.sns import (
    CollectCommentsResponse,
    CollectMetricsResponse,
    IngestResponse,
)
from app.services.sns_collection import (
    COMMENTS_PLATFORMS,
    METRICS_PLATFORMS,
    SUPPORTED_PLATFORMS,
    VALID_PERIODS,
    collect_comments_for_account,
    collect_for_account,
    collect_metrics_for_account,
)

from ._common import internal_router

# ---------------- 내부(시스템) 라우터 ----------------


@internal_router.post("/collect-all", response_model=IngestResponse)
async def collect_all_internal(db: AsyncSession = Depends(get_db)):
    """n8n 등 내부 시스템에서 호출. 자동 수집 가능한 모든 활성 계정 일괄 처리.

    대상: SUPPORTED_PLATFORMS (youtube/facebook/instagram). 그 외 플랫폼은 스킵.
    개별 계정 실패는 격리하고 나머지를 계속 처리한다.
    """
    accounts_q = await db.execute(
        select(SocialAccount).where(
            SocialAccount.is_active.is_(True),
            SocialAccount.platform.in_(SUPPORTED_PLATFORMS),
        )
    )
    accounts = accounts_q.scalars().all()

    posts_added = 0
    posts_updated = 0
    snapshots_added = 0
    snapshots_updated = 0
    failures: list[str] = []

    for account in accounts:
        try:
            result = await collect_for_account(db, account)
            posts_added += result.posts_added
            posts_updated += result.posts_updated
            snapshots_added += result.snapshots_added
            snapshots_updated += result.snapshots_updated
        except HTTPException as exc:
            failures.append(f"{account.platform}/{account.language}: {exc.detail}")
            await db.rollback()

    if failures and (posts_added + posts_updated + snapshots_added + snapshots_updated) == 0:
        # All accounts failed — surface the first error.
        raise HTTPException(status_code=502, detail="; ".join(failures))

    return IngestResponse(
        posts_added=posts_added,
        posts_updated=posts_updated,
        snapshots_added=snapshots_added,
        snapshots_updated=snapshots_updated,
    )


@internal_router.post("/collect-metrics-all", response_model=CollectMetricsResponse)
async def collect_metrics_all_internal(
    period: str = Query("daily", description="daily | weekly"),
    db: AsyncSession = Depends(get_db),
):
    """n8n 일/주 cron 에서 호출. 메트릭 수집 가능한 모든 활성 계정의 게시물 메트릭 수집.

    대상: METRICS_PLATFORMS (facebook/instagram). 개별 계정 실패는 격리.
    period 별로 (post, period, 오늘) 1건만 유지하므로 재호출은 멱등(같은 날이면 갱신).
    """
    if period not in VALID_PERIODS:
        raise HTTPException(status_code=422, detail="period 는 daily 또는 weekly 여야 합니다")

    accounts_q = await db.execute(
        select(SocialAccount).where(
            SocialAccount.is_active.is_(True),
            SocialAccount.platform.in_(METRICS_PLATFORMS),
        )
    )
    accounts = accounts_q.scalars().all()

    processed = 0
    added = 0
    updated = 0
    skipped = 0
    failures: list[str] = []

    for account in accounts:
        try:
            result = await collect_metrics_for_account(db, account, period)
            processed += result.posts_processed
            added += result.snapshots_added
            updated += result.snapshots_updated
            skipped += result.skipped
            failures.extend(result.failures)
        except HTTPException as exc:
            failures.append(f"{account.platform}/{account.language}: {exc.detail}")
            await db.rollback()

    if failures and (processed + added + updated) == 0 and not skipped:
        raise HTTPException(status_code=502, detail="; ".join(failures[:5]))

    return CollectMetricsResponse(
        period=period,
        posts_processed=processed,
        snapshots_added=added,
        snapshots_updated=updated,
        skipped=skipped,
        failures=failures,
    )


@internal_router.post("/collect-comments-all", response_model=CollectCommentsResponse)
async def collect_comments_all_internal(db: AsyncSession = Depends(get_db)):
    """n8n cron 에서 호출. 댓글 수집 가능한 모든 활성 계정의 게시물 댓글 수집.

    대상: COMMENTS_PLATFORMS (facebook/instagram). 개별 계정 실패는 격리.
    (post, 댓글ID) UNIQUE 로 재호출은 멱등.
    """
    accounts_q = await db.execute(
        select(SocialAccount).where(
            SocialAccount.is_active.is_(True),
            SocialAccount.platform.in_(COMMENTS_PLATFORMS),
        )
    )
    accounts = accounts_q.scalars().all()

    processed = 0
    added = 0
    updated = 0
    skipped = 0
    failures: list[str] = []

    for account in accounts:
        try:
            result = await collect_comments_for_account(db, account)
            processed += result.posts_processed
            added += result.comments_added
            updated += result.comments_updated
            skipped += result.skipped
            failures.extend(result.failures)
        except HTTPException as exc:
            failures.append(f"{account.platform}/{account.language}: {exc.detail}")
            await db.rollback()

    if failures and (processed + added + updated) == 0 and not skipped:
        raise HTTPException(status_code=502, detail="; ".join(failures[:5]))

    return CollectCommentsResponse(
        posts_processed=processed,
        comments_added=added,
        comments_updated=updated,
        skipped=skipped,
        failures=failures,
    )
