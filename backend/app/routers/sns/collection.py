"""SNS 수집 트리거 엔드포인트 — ingest / collect / 메트릭 / 전체 갱신.

수집 코어는 services.sns_collection 가 담당하고, 라우터는 HTTP 경계만 처리한다.
"""

import logging

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.sns import SocialAccount, SocialPostMetricSnapshot
from app.schemas.sns import (
    CollectMetricsResponse,
    IngestRequest,
    IngestResponse,
    MetricSnapshotRead,
    RefreshAccountResult,
    RefreshAllResponse,
)
from app.services.sns_collection import (
    METRICS_MAX_POSTS_PER_RUN,
    METRICS_PLATFORMS,
    SUPPORTED_PLATFORMS,
    VALID_PERIODS,
    collect_for_account,
    collect_metrics_for_account,
    upsert_post,
    upsert_snapshot,
)

from ._common import router

logger = logging.getLogger("app.routers.sns")

# ---------------- Ingest ----------------


@router.post("/ingest", response_model=IngestResponse)
async def ingest(body: IngestRequest, db: AsyncSession = Depends(get_db)):
    posts_added = 0
    posts_updated = 0
    snapshots_added = 0
    snapshots_updated = 0

    try:
        for post_payload in body.posts:
            updated = await upsert_post(db, post_payload)
            if updated:
                posts_updated += 1
            else:
                posts_added += 1

        for snap_payload in body.snapshots:
            _, was_updated = await upsert_snapshot(db, snap_payload)
            if was_updated:
                snapshots_updated += 1
            else:
                snapshots_added += 1

        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("SNS ingest 처리 실패")
        raise HTTPException(
            status_code=500, detail=f"수집 처리 실패: {type(exc).__name__}"
        )

    return IngestResponse(
        posts_added=posts_added,
        posts_updated=posts_updated,
        snapshots_added=snapshots_added,
        snapshots_updated=snapshots_updated,
    )


# ---------------- 자동 수집 트리거 ----------------


@router.post(
    "/collect/{account_id}",
    response_model=IngestResponse,
)
async def collect(
    account_id: str,
    full: bool = Query(False, description="True면 전체 페이지네이션, False면 최근 50개만"),
    db: AsyncSession = Depends(get_db),
):
    """마케팅 SNS 담당자가 단일 계정을 수동 트리거(무료 수집). '지금 수집'/'전체 동기화' 버튼이 사용."""
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")
    return await collect_for_account(db, account, full=full)


# ---------------- 게시물 메트릭 시계열 (collect-metrics) ----------------


@router.post(
    "/accounts/{account_id}/collect-metrics",
    response_model=CollectMetricsResponse,
)
async def collect_metrics(
    account_id: str,
    period: str = Query("daily", description="daily | weekly"),
    db: AsyncSession = Depends(get_db),
):
    """단일 계정의 모든 게시물 메트릭을 수집해 시계열 스냅샷으로 저장 (멱등)."""
    if period not in VALID_PERIODS:
        raise HTTPException(status_code=422, detail="period 는 daily 또는 weekly 여야 합니다")
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")
    # 동기(대화형) 호출은 최근 게시물 상한 적용 — nginx 60s 504 회피. 전체는 cron.
    return await collect_metrics_for_account(
        db, account, period, max_posts=METRICS_MAX_POSTS_PER_RUN
    )


@router.get(
    "/posts/{post_id}/metrics",
    response_model=list[MetricSnapshotRead],
)
async def list_post_metrics(
    post_id: str,
    period: str | None = Query(None, description="daily | weekly 로 필터"),
    db: AsyncSession = Depends(get_db),
):
    """게시물의 메트릭 시계열 (오래된→최신)."""
    query = (
        select(SocialPostMetricSnapshot)
        .where(SocialPostMetricSnapshot.post_id == post_id)
        .order_by(SocialPostMetricSnapshot.captured_at.asc())
    )
    if period:
        query = query.where(SocialPostMetricSnapshot.period == period)
    result = await db.execute(query)
    return result.scalars().all()


# ---------------- 전체 갱신 (사용자 트리거) ----------------


async def _refresh_one_account(
    db: AsyncSession,
    account: SocialAccount,
    period: str,
    include_metrics: bool,
) -> RefreshAccountResult:
    """계정 1개 갱신 — 게시물/팔로워 수집 + (옵션) 메트릭 수집. 실패는 격리.

    1) `collect_for_account` 로 게시물·팔로워 스냅샷 수집(모든 플랫폼).
    2) include_metrics 면 fb/ig 한정 `collect_metrics_for_account` 로 메트릭 수집.
       메트릭만 실패해도 1)이 성공했으면 계정은 ok=True(부분 성공)로 본다.
    각 단계는 자체 commit 을 수행하므로, 한 단계 실패 시 rollback 후 다음으로 진행한다.
    """
    label = f"{account.platform}/{account.language}"
    posts_ok = False
    errors: list[str] = []
    posts_added = posts_updated = snapshots_added = snapshots_updated = 0
    metrics_processed = 0

    # 1) 게시물 + 팔로워 스냅샷
    try:
        collected = await collect_for_account(db, account)
        posts_added = collected.posts_added
        posts_updated = collected.posts_updated
        snapshots_added = collected.snapshots_added
        snapshots_updated = collected.snapshots_updated
        posts_ok = True
    except HTTPException as exc:
        await db.rollback()
        errors.append(f"게시물 수집: {exc.detail}")
    except Exception as exc:  # noqa: BLE001 — 계정 단위 격리
        await db.rollback()
        errors.append(f"게시물 수집 실패: {type(exc).__name__}")

    # 2) 메트릭 (fb/ig 한정, 동기 상한 적용)
    if include_metrics and account.platform in METRICS_PLATFORMS:
        try:
            metrics = await collect_metrics_for_account(
                db, account, period, max_posts=METRICS_MAX_POSTS_PER_RUN
            )
            metrics_processed = metrics.posts_processed
            # 게시물별 부분 실패는 metrics.failures 에 누적됨 → 일부만 노출.
            if metrics.failures:
                errors.extend(f"메트릭: {f}" for f in metrics.failures[:3])
        except HTTPException as exc:
            await db.rollback()
            errors.append(f"메트릭 수집: {exc.detail}")
        except Exception as exc:  # noqa: BLE001 — 메트릭 실패는 게시물 성공을 무효화하지 않음
            await db.rollback()
            errors.append(f"메트릭 수집 실패: {type(exc).__name__}")

    return RefreshAccountResult(
        account_id=account.id,
        platform=account.platform,
        language=account.language,
        handle=account.handle,
        ok=posts_ok,
        posts_added=posts_added,
        posts_updated=posts_updated,
        snapshots_added=snapshots_added,
        snapshots_updated=snapshots_updated,
        metrics_processed=metrics_processed,
        errors=errors,
    )


@router.post(
    "/refresh-all",
    response_model=RefreshAllResponse,
)
async def refresh_all(
    include_metrics: bool = Query(
        True,
        description="True면 fb/ig 게시물 메트릭(조회/도달/좋아요 등)까지 수집. "
        "False면 게시물·팔로워만 빠르게 갱신.",
    ),
    period: str = Query("daily", description="메트릭 수집 period: daily | weekly"),
    db: AsyncSession = Depends(get_db),
):
    """마케팅 SNS 담당자가 누르는 '전체 갱신' — 모든 활성 계정을 동기 일괄 수집.

    내부 cron 용 `/api/internal/sns/collect-all`(X-Internal-Token) 과 동일한 수집 로직
    (`collect_for_account`, `collect_metrics_for_account`)을 재사용하며, 라우터의 일반 SNS
    모듈 권한(`require_module(MARKETING_SNS)`)으로만 게이트한다(무료 수집 → 전 직원 개방).

    계정별 실패는 격리(`_refresh_one_account`)하고 계정 단위 성공/실패 요약을 반환한다.
    동기 처리: 계정 수가 소수(현재 3개 수준)이고 nginx /api/ 타임아웃이 300s 이므로
    동기로 충분. 계정·게시물이 크게 늘어 300s 초과가 우려되면 비동기 잡(설계 §2.3 안 A)으로
    전환한다(현재는 미적용).
    """
    if period not in VALID_PERIODS:
        raise HTTPException(status_code=422, detail="period 는 daily 또는 weekly 여야 합니다")

    # 실제 API 연동된 계정(external_id 보유)만 갱신한다. 엑셀 가져오기가 만든
    # 미연동 placeholder 계정(external_id 없음)은 수집 시 세션을 깨뜨려(MissingGreenlet)
    # 전체 갱신을 500으로 터뜨리므로 제외 — 데이터도 없어 갱신 대상이 아니다.
    accounts_q = await db.execute(
        select(SocialAccount).where(
            SocialAccount.is_active.is_(True),
            SocialAccount.platform.in_(SUPPORTED_PLATFORMS),
            SocialAccount.external_id.isnot(None),
            SocialAccount.external_id != "",
        )
    )
    accounts = accounts_q.scalars().all()

    results: list[RefreshAccountResult] = []
    for account in accounts:
        # 한 계정의 예기치 못한 치명적 실패가 전체 갱신을 막지 않도록 한 번 더 격리.
        try:
            results.append(
                await _refresh_one_account(db, account, period, include_metrics)
            )
        except Exception as exc:  # noqa: BLE001
            try:
                await db.rollback()
            except Exception:  # noqa: BLE001 — 세션이 이미 깨진 경우
                logger.exception("전체 갱신: rollback 실패 account=%s", account.id)
            logger.exception("전체 갱신: 계정 격리 실패 account=%s", account.id)
            results.append(
                RefreshAccountResult(
                    account_id=account.id,
                    platform=account.platform,
                    language=account.language,
                    handle=account.handle,
                    ok=False,
                    posts_added=0,
                    posts_updated=0,
                    snapshots_added=0,
                    snapshots_updated=0,
                    metrics_processed=0,
                    errors=[f"갱신 실패: {type(exc).__name__}"],
                )
            )

    ok_count = sum(1 for r in results if r.ok)
    failed_count = sum(1 for r in results if not r.ok)
    return RefreshAllResponse(
        ok_count=ok_count,
        failed_count=failed_count,
        total=len(results),
        include_metrics=include_metrics,
        results=results,
    )
