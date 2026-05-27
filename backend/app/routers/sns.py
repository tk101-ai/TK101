import io
import os
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import Integer, and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_internal_token, require_module
from app.models.sns import (
    SocialAccount,
    SocialPost,
    SocialPostMetricSnapshot,
    SocialWeeklySnapshot,
)
from app.modules.constants import Module
from app.schemas.sns import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    CollectMetricsResponse,
    ContentCreate,
    GrowthCard,
    ImportResponse,
    IngestRequest,
    IngestResponse,
    MetricSnapshotRead,
    PostCreate,
    PostRead,
    PostUpdate,
    SnapshotCreate,
    SnapshotRead,
    TopPost,
    WeeklyKpiRow,
)
from app.services.sns_collectors.base import BaseCollector, CollectorError

# 자동 수집 가능한 플랫폼. Collector 추가 시 여기에 등록.
SUPPORTED_PLATFORMS = ("youtube", "facebook", "instagram")
# 메트릭 시계열(collect-metrics)을 지원하는 플랫폼.
METRICS_PLATFORMS = ("facebook", "instagram")
VALID_PERIODS = ("daily", "weekly")

router = APIRouter(
    prefix="/api/sns",
    tags=["sns"],
    dependencies=[Depends(require_module(Module.MARKETING_SNS.value))],
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------- 계정 ----------------


@router.get("/accounts", response_model=list[AccountRead])
async def list_accounts(
    platform: str | None = Query(None),
    language: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(SocialAccount).order_by(SocialAccount.platform, SocialAccount.language)
    if platform:
        query = query.where(SocialAccount.platform == platform)
    if language:
        query = query.where(SocialAccount.language == language)
    if is_active is not None:
        query = query.where(SocialAccount.is_active == is_active)
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/accounts",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_account(body: AccountCreate, db: AsyncSession = Depends(get_db)):
    account = SocialAccount(**body.model_dump())
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountRead,
    dependencies=[Depends(require_admin)],
)
async def update_account(account_id: str, body: AccountUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    await db.commit()
    await db.refresh(account)
    return account


# ---------------- 콘텐츠 (Post) ----------------


@router.get("/posts", response_model=list[PostRead])
async def list_posts(
    account_id: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    content_type: str | None = Query(None),
    language: str | None = Query(None),
    platform: str | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    query = select(SocialPost).order_by(SocialPost.posted_at.desc())
    if account_id:
        query = query.where(SocialPost.account_id == account_id)
    if date_from:
        query = query.where(SocialPost.posted_at >= date_from)
    if date_to:
        query = query.where(SocialPost.posted_at <= date_to)
    if content_type:
        query = query.where(SocialPost.content_type == content_type)
    if language or platform:
        query = query.join(SocialAccount, SocialAccount.id == SocialPost.account_id)
        if language:
            query = query.where(SocialAccount.language == language)
        if platform:
            query = query.where(SocialAccount.platform == platform)
    result = await db.execute(query.limit(limit).offset(offset))
    return result.scalars().all()


@router.post("/posts", response_model=PostRead, status_code=status.HTTP_201_CREATED)
async def create_post(body: PostCreate, db: AsyncSession = Depends(get_db)):
    post = SocialPost(**body.model_dump())
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


@router.patch("/posts/{post_id}", response_model=PostRead)
async def update_post(post_id: str, body: PostUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SocialPost).where(SocialPost.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="게시물을 찾을 수 없습니다")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    await db.commit()
    await db.refresh(post)
    return post


# ---------------- 주간 스냅샷 ----------------


async def _upsert_snapshot(db: AsyncSession, payload: SnapshotCreate) -> tuple[SocialWeeklySnapshot, bool]:
    """Return (snapshot, was_updated). True if existing row updated, False if newly inserted."""
    result = await db.execute(
        select(SocialWeeklySnapshot).where(
            and_(
                SocialWeeklySnapshot.account_id == payload.account_id,
                SocialWeeklySnapshot.year == payload.year,
                SocialWeeklySnapshot.month == payload.month,
                SocialWeeklySnapshot.week_number == payload.week_number,
            )
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.followers = payload.followers
        existing.captured_at = datetime.now(tz=timezone.utc)
        return existing, True
    snap = SocialWeeklySnapshot(**payload.model_dump())
    db.add(snap)
    return snap, False


@router.get("/snapshots", response_model=list[SnapshotRead])
async def list_snapshots(
    account_id: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(SocialWeeklySnapshot).order_by(
        SocialWeeklySnapshot.year.desc(),
        SocialWeeklySnapshot.month.desc(),
        SocialWeeklySnapshot.week_number.desc(),
    )
    if account_id:
        query = query.where(SocialWeeklySnapshot.account_id == account_id)
    if year is not None:
        query = query.where(SocialWeeklySnapshot.year == year)
    if month is not None:
        query = query.where(SocialWeeklySnapshot.month == month)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/snapshots", response_model=SnapshotRead, status_code=status.HTTP_201_CREATED)
async def create_snapshot(body: SnapshotCreate, db: AsyncSession = Depends(get_db)):
    snap, _ = await _upsert_snapshot(db, body)
    await db.commit()
    await db.refresh(snap)
    return snap


@router.post("/snapshots/bulk", response_model=list[SnapshotRead])
async def bulk_snapshots(body: list[SnapshotCreate], db: AsyncSession = Depends(get_db)):
    saved: list[SocialWeeklySnapshot] = []
    for item in body:
        snap, _ = await _upsert_snapshot(db, item)
        saved.append(snap)
    await db.commit()
    for s in saved:
        await db.refresh(s)
    return saved


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
    snap_q = select(
        SocialAccount.language.label("language"),
        SocialAccount.platform.label("platform"),
        SocialWeeklySnapshot.year.label("year"),
        SocialWeeklySnapshot.month.label("month"),
        SocialWeeklySnapshot.week_number.label("week_number"),
        func.sum(SocialWeeklySnapshot.followers).label("followers"),
    ).join(SocialAccount, SocialAccount.id == SocialWeeklySnapshot.account_id).where(
        SocialWeeklySnapshot.year == year
    ).group_by(
        SocialAccount.language,
        SocialAccount.platform,
        SocialWeeklySnapshot.year,
        SocialWeeklySnapshot.month,
        SocialWeeklySnapshot.week_number,
    )
    if month is not None:
        snap_q = snap_q.where(SocialWeeklySnapshot.month == month)

    snap_result = await db.execute(snap_q)
    snap_rows = snap_result.all()

    # Posts aggregated by (language, platform, year, month, week_of_month).
    # week_of_month = ((day-1)/7) + 1 to align with snapshot's week_number(1-5).
    week_of_month = (((func.extract("day", SocialPost.posted_at) - 1) / 7).cast(Integer) + 1).label("week_number")
    post_year = func.extract("year", SocialPost.posted_at).cast(Integer).label("year")
    post_month = func.extract("month", SocialPost.posted_at).cast(Integer).label("month")

    post_q = select(
        SocialAccount.language.label("language"),
        SocialAccount.platform.label("platform"),
        post_year,
        post_month,
        week_of_month,
        func.count(SocialPost.id).label("post_count"),
        func.coalesce(func.sum(SocialPost.view_count), 0).label("view_count"),
        func.coalesce(
            func.sum(
                func.coalesce(SocialPost.like_count, 0)
                + func.coalesce(SocialPost.comment_count, 0)
                + func.coalesce(SocialPost.share_count, 0)
            ),
            0,
        ).label("reaction_count"),
    ).join(SocialAccount, SocialAccount.id == SocialPost.account_id).where(
        func.extract("year", SocialPost.posted_at) == year
    ).group_by(
        SocialAccount.language,
        SocialAccount.platform,
        post_year,
        post_month,
        week_of_month,
    )
    if month is not None:
        post_q = post_q.where(func.extract("month", SocialPost.posted_at) == month)

    post_result = await db.execute(post_q)
    post_map: dict[tuple, tuple[int, int, int]] = {}
    for r in post_result.all():
        key = (r.language, r.platform, int(r.year), int(r.month), int(r.week_number))
        post_map[key] = (int(r.post_count), int(r.view_count), int(r.reaction_count))

    rows: list[WeeklyKpiRow] = []
    for r in snap_rows:
        key = (r.language, r.platform, r.year, r.month, r.week_number)
        post_count, view_count, reaction_count = post_map.get(key, (0, 0, 0))
        rows.append(
            WeeklyKpiRow(
                language=r.language,
                platform=r.platform,
                year=r.year,
                month=r.month,
                week_number=r.week_number,
                followers=int(r.followers or 0),
                post_count=post_count,
                view_count=view_count,
                reaction_count=reaction_count,
            )
        )
    return rows


@router.get("/stats/growth", response_model=list[GrowthCard])
async def stats_growth(db: AsyncSession = Depends(get_db)):
    """채널별 최신 스냅샷 vs 직전 스냅샷 비교."""
    accounts_result = await db.execute(
        select(SocialAccount).where(SocialAccount.is_active.is_(True))
    )
    accounts = accounts_result.scalars().all()

    cards: list[GrowthCard] = []
    for acc in accounts:
        snap_result = await db.execute(
            select(SocialWeeklySnapshot)
            .where(SocialWeeklySnapshot.account_id == acc.id)
            .order_by(
                SocialWeeklySnapshot.year.desc(),
                SocialWeeklySnapshot.month.desc(),
                SocialWeeklySnapshot.week_number.desc(),
            )
            .limit(2)
        )
        snaps = snap_result.scalars().all()
        if not snaps:
            continue
        current = snaps[0].followers
        prev = snaps[1].followers if len(snaps) > 1 else current
        growth_rate = 0.0
        if prev > 0:
            growth_rate = (current - prev) / prev
        cards.append(
            GrowthCard(
                language=acc.language,
                platform=acc.platform,
                current_followers=current,
                prev_followers=prev,
                growth_rate=growth_rate,
            )
        )
    return cards


@router.get("/stats/top-posts", response_model=list[TopPost])
async def stats_top_posts(
    limit: int = Query(5, ge=1, le=50),
    language: str | None = Query(None),
    platform: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(
            SocialPost.id,
            SocialPost.posted_at,
            SocialPost.title,
            SocialAccount.language,
            SocialAccount.platform,
            SocialPost.view_count,
            SocialPost.total_engagement,
            SocialPost.url,
        )
        .join(SocialAccount, SocialAccount.id == SocialPost.account_id)
        .order_by(SocialPost.total_engagement.desc().nullslast())
        .limit(limit)
    )
    if language:
        query = query.where(SocialAccount.language == language)
    if platform:
        query = query.where(SocialAccount.platform == platform)
    result = await db.execute(query)
    return [
        TopPost(
            id=row.id,
            posted_at=row.posted_at,
            title=row.title,
            language=row.language,
            platform=row.platform,
            view_count=row.view_count,
            total_engagement=row.total_engagement,
            url=row.url,
        )
        for row in result.all()
    ]


@router.get("/stats/trend")
async def stats_trend(
    language: str | None = Query(None),
    platform: str | None = Query(None),
):
    """주차별 누적 트렌드. 차트 위젯에서 활용. 현재는 placeholder."""
    return []


# ---------------- Ingest ----------------


async def _upsert_post(db: AsyncSession, payload: PostCreate) -> bool:
    """Upsert a single post. Returns True if updated, False if inserted."""
    existing: SocialPost | None = None
    if payload.external_id:
        result = await db.execute(
            select(SocialPost).where(
                and_(
                    SocialPost.account_id == payload.account_id,
                    SocialPost.external_id == payload.external_id,
                )
            )
        )
        existing = result.scalar_one_or_none()
    else:
        result = await db.execute(
            select(SocialPost).where(
                and_(
                    SocialPost.account_id == payload.account_id,
                    SocialPost.posted_at == payload.posted_at,
                    SocialPost.title == payload.title,
                    SocialPost.url == payload.url,
                )
            )
        )
        existing = result.scalar_one_or_none()

    data = payload.model_dump()
    if existing is not None:
        for field, value in data.items():
            setattr(existing, field, value)
        return True
    db.add(SocialPost(**data))
    return False


@router.post("/ingest", response_model=IngestResponse)
async def ingest(body: IngestRequest, db: AsyncSession = Depends(get_db)):
    posts_added = 0
    posts_updated = 0
    snapshots_added = 0
    snapshots_updated = 0

    try:
        for post_payload in body.posts:
            updated = await _upsert_post(db, post_payload)
            if updated:
                posts_updated += 1
            else:
                posts_added += 1

        for snap_payload in body.snapshots:
            _, was_updated = await _upsert_snapshot(db, snap_payload)
            if was_updated:
                snapshots_updated += 1
            else:
                snapshots_added += 1

        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"수집 처리 실패: {exc}")

    return IngestResponse(
        posts_added=posts_added,
        posts_updated=posts_updated,
        snapshots_added=snapshots_added,
        snapshots_updated=snapshots_updated,
    )


# ---------------- 자동 수집 트리거 ----------------


def _current_iso_week_parts(today: date | None = None) -> tuple[int, int, int]:
    """Return (year, month, week_of_month) where week_of_month uses 1-5 scheme matching snapshots."""
    today = today or date.today()
    week_of_month = ((today.day - 1) // 7) + 1
    return today.year, today.month, week_of_month


async def _build_collector(account: SocialAccount) -> BaseCollector:
    """플랫폼별 수집기 생성. 토큰/식별자 문제는 명확한 HTTP 에러(한국어)로 변환.

    - youtube: YouTubeCollector (채널 ID/핸들 resolve, external_id 백필).
    - facebook/instagram: Meta Graph 수집기. 토큰 미설정 시 CollectorError → 503.
    """
    platform = account.platform
    if platform not in SUPPORTED_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"'{platform}' 플랫폼 자동 수집은 아직 구현되지 않았습니다",
        )

    try:
        if platform == "youtube":
            from app.services.sns_collectors.youtube import YouTubeCollector

            return await YouTubeCollector.from_account(account)
        if platform == "facebook":
            from app.services.sns_collectors.facebook import FacebookCollector

            return await FacebookCollector.from_account(account)
        from app.services.sns_collectors.instagram import InstagramCollector

        return await InstagramCollector.from_account(account)
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"수집기 로딩 실패: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except CollectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


async def _collect_for_account(
    db: AsyncSession,
    account: SocialAccount,
    full: bool = False,
) -> IngestResponse:
    """Run the appropriate collector for an account and persist results.

    Supports youtube / facebook / instagram (see SUPPORTED_PLATFORMS).
    YouTube writes the resolved channel_id back to account.external_id so
    subsequent calls skip handle resolution. Meta collectors read posts +
    follower count via the Graph API.

    full=True paginates through every item (use for first sync / backfill).
    full=False (default) is the cheap path used by the weekly cron.
    """
    collector = await _build_collector(account)

    # YouTube: persist resolved channel_id to skip the resolution call next time.
    channel_id = getattr(collector, "channel_id", None)
    if channel_id and account.external_id != channel_id:
        account.external_id = channel_id

    try:
        if account.platform == "youtube":
            collected_posts = await collector.fetch_posts(full=full)  # type: ignore[call-arg]
        else:
            collected_posts = await collector.fetch_posts()
        followers = await collector.fetch_followers()
    except CollectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"외부 API 호출 실패: {exc}")

    posts_added = 0
    posts_updated = 0
    snapshots_added = 0
    snapshots_updated = 0

    try:
        for cp in collected_posts:
            payload = PostCreate(account_id=account.id, **cp)
            updated = await _upsert_post(db, payload)
            if updated:
                posts_updated += 1
            else:
                posts_added += 1

        year, month, week_number = _current_iso_week_parts()
        snap_payload = SnapshotCreate(
            account_id=account.id,
            year=year,
            month=month,
            week_number=week_number,
            followers=int(followers),
        )
        _, was_updated = await _upsert_snapshot(db, snap_payload)
        if was_updated:
            snapshots_updated += 1
        else:
            snapshots_added += 1

        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"수집 데이터 저장 실패: {exc}")

    return IngestResponse(
        posts_added=posts_added,
        posts_updated=posts_updated,
        snapshots_added=snapshots_added,
        snapshots_updated=snapshots_updated,
    )


@router.post(
    "/collect/{account_id}",
    response_model=IngestResponse,
    dependencies=[Depends(require_admin)],
)
async def collect(
    account_id: str,
    full: bool = Query(False, description="True면 전체 페이지네이션, False면 최근 50개만"),
    db: AsyncSession = Depends(get_db),
):
    """관리자가 단일 계정을 수동 트리거. SnsAccounts 페이지의 '지금 수집'/'전체 동기화' 버튼이 사용."""
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")
    return await _collect_for_account(db, account, full=full)


# ---------------- 수동 콘텐츠 등록 (FALLBACK 모드) ----------------


@router.post(
    "/accounts/{account_id}/contents",
    response_model=PostRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_content(
    account_id: str,
    body: ContentCreate,
    db: AsyncSession = Depends(get_db),
):
    """수동 콘텐츠 1행 등록 (배포일/제목/형태/제작주체/URL). is_manual=true.

    메타 토큰이 없어도 동작하는 FALLBACK 경로. 등록 후 collect-metrics 가
    조회수/좋아요/댓글/공유를 일/주 주기로 채운다.
    """
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")

    post = SocialPost(
        account_id=account.id,
        posted_at=body.posted_at,
        title=body.title,
        content_type=body.content_type,
        producer=body.producer,
        url=body.url,
        external_id=body.external_id,
        is_manual=True,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


# ---------------- 게시물 메트릭 시계열 (collect-metrics) ----------------


def _post_ref(post: SocialPost) -> str | None:
    """수집기에 넘길 게시물 참조값. external_id 우선, 없으면 URL."""
    return post.external_id or post.url


async def _upsert_metric_snapshot(
    db: AsyncSession,
    post_id,
    period: str,
    metrics,
) -> bool:
    """오늘 날짜·period 기준 메트릭 스냅샷 upsert. True=업데이트, False=신규.

    (post_id, period, captured_at::date) UNIQUE 와 정합 — 오늘자 행을 찾으면 갱신.
    """
    today = date.today()
    result = await db.execute(
        select(SocialPostMetricSnapshot).where(
            SocialPostMetricSnapshot.post_id == post_id,
            SocialPostMetricSnapshot.period == period,
            func.date(SocialPostMetricSnapshot.captured_at) == today,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.views = metrics.get("views")
        existing.reach = metrics.get("reach")
        existing.likes = metrics.get("likes")
        existing.comments = metrics.get("comments")
        existing.shares = metrics.get("shares")
        existing.engagement_total = metrics.get("engagement_total")
        existing.raw = metrics.get("raw")
        existing.captured_at = datetime.now(tz=timezone.utc)
        return True
    db.add(
        SocialPostMetricSnapshot(
            post_id=post_id,
            period=period,
            views=metrics.get("views"),
            reach=metrics.get("reach"),
            likes=metrics.get("likes"),
            comments=metrics.get("comments"),
            shares=metrics.get("shares"),
            engagement_total=metrics.get("engagement_total"),
            raw=metrics.get("raw"),
        )
    )
    return False


async def _collect_metrics_for_account(
    db: AsyncSession,
    account: SocialAccount,
    period: str,
) -> CollectMetricsResponse:
    """계정의 모든 게시물에 대해 fetch_post_metrics → 메트릭 스냅샷 upsert."""
    if account.platform not in METRICS_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"'{account.platform}' 는 게시물 메트릭 수집을 지원하지 않습니다",
        )

    collector = await _build_collector(account)
    posts_result = await db.execute(
        select(SocialPost).where(SocialPost.account_id == account.id)
    )
    posts = posts_result.scalars().all()

    processed = 0
    added = 0
    updated = 0
    skipped = 0
    failures: list[str] = []

    for post in posts:
        ref = _post_ref(post)
        if not ref:
            skipped += 1
            continue
        try:
            metrics = await collector.fetch_post_metrics(ref)
        except CollectorError as exc:
            failures.append(f"{ref}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 — 개별 게시물 실패는 격리
            failures.append(f"{ref}: {exc}")
            continue
        was_updated = await _upsert_metric_snapshot(db, post.id, period, metrics)
        processed += 1
        if was_updated:
            updated += 1
        else:
            added += 1

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"메트릭 저장 실패: {exc}")

    return CollectMetricsResponse(
        period=period,
        posts_processed=processed,
        snapshots_added=added,
        snapshots_updated=updated,
        skipped=skipped,
        failures=failures,
    )


@router.post(
    "/accounts/{account_id}/collect-metrics",
    response_model=CollectMetricsResponse,
    dependencies=[Depends(require_admin)],
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
    return await _collect_metrics_for_account(db, account, period)


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


@router.delete(
    "/accounts/{account_id}/posts",
    dependencies=[Depends(require_admin)],
    status_code=status.HTTP_200_OK,
)
async def reset_account_posts(account_id: str, db: AsyncSession = Depends(get_db)):
    """해당 계정의 모든 콘텐츠를 삭제. 주간 팔로워 스냅샷은 보존.

    엑셀 import 데이터를 비우고 자동 수집 결과로 다시 채우려는 케이스 등에 사용.
    """
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")
    delete_result = await db.execute(
        delete(SocialPost).where(SocialPost.account_id == account_id)
    )
    deleted = delete_result.rowcount or 0
    await db.commit()
    return {"deleted": deleted}


# ---------------- 내부(시스템) 라우터 ----------------

internal_router = APIRouter(
    prefix="/api/internal/sns",
    tags=["sns-internal"],
    dependencies=[Depends(require_internal_token)],
)


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
            result = await _collect_for_account(db, account)
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
            result = await _collect_metrics_for_account(db, account, period)
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


# ---------------- 엑셀 임포트 ----------------


@router.post("/import/marketing1-excel", response_model=ImportResponse)
async def import_marketing1_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="파일 크기 초과 (최대 10MB)")

    safe_filename = os.path.basename(file.filename or "marketing1.xlsx")
    if not safe_filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=415, detail="엑셀 파일(.xlsx/.xls)만 업로드 가능합니다")

    try:
        from app.services.sns_importers.marketing1 import import_to_db, parse_workbook
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"임포터 로딩 실패: {exc}")

    try:
        parsed = parse_workbook(io.BytesIO(contents))
        result = await import_to_db(db, parsed)
        await db.commit()
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail=f"엑셀 파싱 실패: {exc}")
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"임포트 실패: {exc}")

    return ImportResponse(
        accounts_added=result.get("accounts_added", 0),
        snapshots_added=result.get("snapshots_added", 0),
        posts_added=result.get("posts_added", 0),
        posts_updated=result.get("posts_updated", 0),
    )
