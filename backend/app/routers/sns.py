import io
import logging
import os
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import Integer, and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_internal_token, require_module
from app.models.sns import (
    SocialAccount,
    SocialPost,
    SocialPostComment,
    SocialPostMetricSnapshot,
    SocialWeeklySnapshot,
)
from app.modules.constants import Module
from app.config import settings
from app.schemas.sns import (
    AccountCreate,
    AccountDeleteResponse,
    AccountRead,
    AccountUpdate,
    CollectCommentsResponse,
    CommentAnalysisResponse,
    CollectMetricsResponse,
    CommentRead,
    CommentTranslateResponse,
    ContentCreate,
    GrowthCard,
    ImportResponse,
    IngestRequest,
    IngestResponse,
    MetricSnapshotRead,
    PostCreate,
    PostRead,
    PostUpdate,
    RefreshAccountResult,
    RefreshAllResponse,
    SnapshotCreate,
    SnapshotRead,
    TopPost,
    TrendPoint,
    WeeklyKpiRow,
)
from app.services.sns_collectors.base import BaseCollector, CollectorError

logger = logging.getLogger(__name__)

# 자동 수집 가능한 플랫폼. Collector 추가 시 여기에 등록.
SUPPORTED_PLATFORMS = ("youtube", "facebook", "instagram")
# 메트릭 시계열(collect-metrics)을 지원하는 플랫폼.
METRICS_PLATFORMS = ("facebook", "instagram")
# 댓글 본문(collect-comments)을 지원하는 플랫폼 (소유/관리 계정 한정).
COMMENTS_PLATFORMS = ("facebook", "instagram")
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


@router.delete(
    "/accounts/{account_id}",
    response_model=AccountDeleteResponse,
    dependencies=[Depends(require_admin)],
)
async def delete_account(
    account_id: str,
    hard: bool = Query(
        False,
        description="True면 계정과 모든 하위 데이터(게시물·스냅샷·메트릭·댓글)를 영구 삭제. "
        "기본(False)은 소프트삭제(is_active=False)로 수집 이력을 보존한다.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """계정 삭제.

    - 기본(`hard=false`): 소프트삭제 — `is_active=False`로 비활성화하고 모든 이력은 보존한다.
      `PATCH`의 소프트삭제와 동일한 결과이나, 의미가 명확한 전용 엔드포인트.
    - `hard=true`: 영구 삭제 — 계정 행을 실제로 DELETE 한다. FK `ON DELETE CASCADE`로
      하위 SocialPost / SocialWeeklySnapshot (그리고 post에 딸린 metric snapshot·comment)이
      함께 정리된다. **수집된 트렌드/메트릭 이력까지 영구 소실**되므로 호출 측에서 명시적 확인 필요.

    없는 계정이면 404.
    """
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")

    if not hard:
        account.is_active = False
        await db.commit()
        return AccountDeleteResponse(id=account.id, hard=False, deleted=False)

    # 하드삭제: 단일 트랜잭션. CASCADE FK가 metric snapshot·comment를 정리하지만,
    # 삭제 건수를 응답에 담기 위해 posts/snapshots는 명시적으로 카운트 후 삭제한다.
    account_uuid = account.id
    posts_deleted = await db.scalar(
        select(func.count(SocialPost.id)).where(SocialPost.account_id == account_uuid)
    )
    snapshots_deleted = await db.scalar(
        select(func.count(SocialWeeklySnapshot.id)).where(
            SocialWeeklySnapshot.account_id == account_uuid
        )
    )
    # 계정 행 삭제 → CASCADE로 posts(→metrics/comments)·snapshots 동반 삭제.
    await db.delete(account)
    await db.commit()
    return AccountDeleteResponse(
        id=account_uuid,
        hard=True,
        deleted=True,
        posts_deleted=int(posts_deleted or 0),
        snapshots_deleted=int(snapshots_deleted or 0),
    )


# ---------------- Meta 토큰 진단 (admin) ----------------


@router.get("/meta/whoami", dependencies=[Depends(require_admin)])
async def meta_whoami():
    """현재 META_ACCESS_TOKEN 이 무엇이고 어떤 페이지/IG 자산을 볼 수 있는지 진단.

    수집 권한 오류(code 10/100) 원인 파악용. 페이지 토큰은 노출하지 않고 보유 여부만.
    """
    from app.services.sns_collectors.base import CollectorError
    from app.services.sns_collectors.meta_graph import graph_get

    try:
        me = await graph_get("me", params={"fields": "id,name"})
        accounts = await graph_get(
            "me/accounts",
            params={
                "fields": "id,name,tasks,access_token,instagram_business_account"
            },
        )
    except CollectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    pages = []
    for p in accounts.get("data") or []:
        ig = p.get("instagram_business_account") or {}
        pages.append(
            {
                "page_id": p.get("id"),
                "name": p.get("name"),
                "tasks": p.get("tasks"),
                "has_page_token": bool(p.get("access_token")),
                "instagram_business_account_id": ig.get("id"),
            }
        )
    return {"me": me, "pages": pages}


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
    # 최근 N개월 경계 계산 (현재 달 기준). year*12+month 정수 비교로 단순화.
    today = date.today()
    boundary = today.year * 12 + today.month - (months - 1)

    query = (
        select(
            SocialWeeklySnapshot.account_id.label("account_id"),
            SocialAccount.platform.label("platform"),
            SocialAccount.language.label("language"),
            SocialAccount.handle.label("handle"),
            SocialWeeklySnapshot.year.label("year"),
            SocialWeeklySnapshot.month.label("month"),
            SocialWeeklySnapshot.week_number.label("week_number"),
            SocialWeeklySnapshot.followers.label("followers"),
        )
        .join(SocialAccount, SocialAccount.id == SocialWeeklySnapshot.account_id)
        .where(
            (SocialWeeklySnapshot.year * 12 + SocialWeeklySnapshot.month) >= boundary
        )
        .order_by(
            SocialWeeklySnapshot.year.asc(),
            SocialWeeklySnapshot.month.asc(),
            SocialWeeklySnapshot.week_number.asc(),
        )
    )
    if language:
        query = query.where(SocialAccount.language == language)
    if platform:
        query = query.where(SocialAccount.platform == platform)
    if account_id:
        query = query.where(SocialWeeklySnapshot.account_id == account_id)

    result = await db.execute(query)
    return [
        TrendPoint(
            account_id=row.account_id,
            platform=row.platform,
            language=row.language,
            handle=row.handle,
            year=int(row.year),
            month=int(row.month),
            week_number=int(row.week_number),
            period=f"{int(row.year)}-{int(row.month):02d}-W{int(row.week_number)}",
            followers=int(row.followers or 0),
        )
        for row in result.all()
    ]


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


def _writeback_post_metrics(post: SocialPost, metrics) -> None:
    """수집한 메트릭을 게시물 컬럼에 반영해 목록/통계에서 바로 보이게 한다.

    None 값은 해당 플랫폼이 제공하지 않는 지표이므로 기존 값을 보존(덮어쓰지 않음).
    예) FB 일반 게시물은 조회수(views)를 제공하지 않으므로 view_count 를 건드리지 않는다.
    """
    if metrics.get("views") is not None:
        post.view_count = metrics.get("views")
    if metrics.get("reach") is not None:
        post.reach_count = metrics.get("reach")
    if metrics.get("likes") is not None:
        post.like_count = metrics.get("likes")
    if metrics.get("comments") is not None:
        post.comment_count = metrics.get("comments")
    if metrics.get("shares") is not None:
        post.share_count = metrics.get("shares")
    if metrics.get("engagement_total") is not None:
        post.total_engagement = metrics.get("engagement_total")


async def _sync_account_posts(
    db: AsyncSession, account: SocialAccount, collector: BaseCollector
) -> tuple[int, int]:
    """메트릭 수집 전 최신 게시물 목록을 동기화. (추가, 갱신) 수 반환.

    '메트릭 수집' 한 번으로 신규 게시물도 함께 반영되도록 fetch_posts → upsert 한다.
    좋아요/댓글 집계(comment_count 등)도 최신화되어 이후 댓글 수집의 0댓글 스킵 판단이
    정확해진다. 팔로워 주간 스냅샷도 함께 갱신(실패는 격리). commit 은 caller 담당.
    """
    if account.platform == "youtube":
        collected = await collector.fetch_posts(full=False)  # type: ignore[call-arg]
    else:
        collected = await collector.fetch_posts()
    added = 0
    updated = 0
    for cp in collected:
        payload = PostCreate(account_id=account.id, **cp)
        if await _upsert_post(db, payload):
            updated += 1
        else:
            added += 1
    try:
        followers = await collector.fetch_followers()
        year, month, week_number = _current_iso_week_parts()
        await _upsert_snapshot(
            db,
            SnapshotCreate(
                account_id=account.id,
                year=year,
                month=month,
                week_number=week_number,
                followers=int(followers),
            ),
        )
    except Exception:  # noqa: BLE001 — 팔로워 동기화 실패는 메트릭 수집을 막지 않음
        logger.warning("팔로워 스냅샷 갱신 실패: account=%s", account.id, exc_info=True)
    await db.flush()
    return added, updated


async def _upsert_metric_snapshot(
    db: AsyncSession,
    post_id,
    period: str,
    metrics,
) -> bool:
    """오늘 날짜·period 기준 메트릭 스냅샷 upsert. True=업데이트, False=신규.

    (post_id, period, captured_at::date) UNIQUE 와 정합 — 오늘자 행을 찾으면 갱신.
    """
    # 인덱스 (captured_at AT TIME ZONE 'UTC')::date 와 동일하게 UTC 일 경계로 조회.
    # date.today()/func.date() 는 세션 TZ 의존이라 인덱스와 어긋나 IntegrityError 위험.
    now_utc = datetime.now(tz=timezone.utc)
    day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1)
    result = await db.execute(
        select(SocialPostMetricSnapshot).where(
            SocialPostMetricSnapshot.post_id == post_id,
            SocialPostMetricSnapshot.period == period,
            SocialPostMetricSnapshot.captured_at >= day_start,
            SocialPostMetricSnapshot.captured_at < day_end,
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


# 동기(대화형) 메트릭 수집 1회 처리 게시물 상한 — nginx 60s 타임아웃(504) 회피.
# 게시물당 2회 Graph 호출(post + insights)이라 댓글 수집보다 무겁다.
# 최근 게시물 우선. 전체 백필은 internal cron(max_posts=None)이 담당.
METRICS_MAX_POSTS_PER_RUN = 20


async def _collect_metrics_for_account(
    db: AsyncSession,
    account: SocialAccount,
    period: str,
    *,
    max_posts: int | None = None,
) -> CollectMetricsResponse:
    """신규 게시물 동기화 → 게시물별 메트릭 스냅샷 upsert + 게시물 컬럼 write-back.

    max_posts 지정 시 최근 게시물 그만큼만 처리(동기 호출 60s 회피). None이면 전체.
    """
    if account.platform not in METRICS_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"'{account.platform}' 는 게시물 메트릭 수집을 지원하지 않습니다",
        )

    collector = await _build_collector(account)

    # 1) 신규 게시물 동기화 — '메트릭 수집' 한 번으로 최근 게시물도 갱신되게 한다.
    #    동기화 실패(권한/네트워크)는 기존 게시물 메트릭 수집을 막지 않도록 격리한다.
    posts_added = 0
    posts_updated = 0
    sync_failures: list[str] = []
    try:
        posts_added, posts_updated = await _sync_account_posts(db, account, collector)
    except CollectorError as exc:
        sync_failures.append(f"게시물 동기화: {exc}")
    except Exception as exc:  # noqa: BLE001 — 동기화 실패해도 메트릭은 진행
        sync_failures.append(f"게시물 동기화 실패: {exc}")

    # 2) (동기화 반영된) 게시물 목록으로 메트릭 수집. 최근 게시물 우선.
    posts_query = (
        select(SocialPost)
        .where(SocialPost.account_id == account.id)
        .order_by(SocialPost.posted_at.desc())
    )
    if max_posts:
        posts_query = posts_query.limit(max_posts)
    posts_result = await db.execute(posts_query)
    posts = posts_result.scalars().all()

    processed = 0
    added = 0
    updated = 0
    skipped = 0
    failures: list[str] = list(sync_failures)

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
        _writeback_post_metrics(post, metrics)
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
        posts_added=posts_added,
        posts_updated=posts_updated,
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
    # 동기(대화형) 호출은 최근 게시물 상한 적용 — nginx 60s 504 회피. 전체는 cron.
    return await _collect_metrics_for_account(
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


# ---------------- 게시물 댓글 (collect-comments) ----------------


async def _upsert_comment(db: AsyncSession, post_id, comment) -> bool:
    """(post_id, external_comment_id) 기준 댓글 upsert. True=업데이트, False=신규.

    external_comment_id 가 없으면(이론상 거의 없음) 매번 신규로 저장하지 않고 skip 신호로
    False 를 주되, caller 가 external_id 유무를 먼저 확인한다.
    """
    external_id = comment.get("external_id")
    result = await db.execute(
        select(SocialPostComment).where(
            SocialPostComment.post_id == post_id,
            SocialPostComment.external_comment_id == external_id,
        )
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        existing.author = comment.get("author")
        existing.text = comment.get("text")
        existing.commented_at = comment.get("commented_at")
        existing.like_count = comment.get("like_count")
        existing.raw = comment.get("raw")
        return True
    db.add(
        SocialPostComment(
            post_id=post_id,
            external_comment_id=external_id,
            author=comment.get("author"),
            text=comment.get("text"),
            commented_at=comment.get("commented_at"),
            like_count=comment.get("like_count"),
            raw=comment.get("raw"),
        )
    )
    return False


# 대화형 댓글 수집 1회 처리 게시물 상한 — nginx 60s 타임아웃 회피.
# 최근 게시물 우선. 전체 백필이 필요하면 cron 을 반복 호출(멱등).
COMMENTS_MAX_POSTS_PER_RUN = 25


async def _collect_comments_for_account(
    db: AsyncSession,
    account: SocialAccount,
    *,
    max_posts: int = COMMENTS_MAX_POSTS_PER_RUN,
) -> CollectCommentsResponse:
    """계정의 최근 게시물에 대해 fetch_comments → 댓글 upsert (멱등).

    소유/관리 계정의 게시물에만 동작 (Graph API 제약). 개별 게시물 실패는 격리.
    최근 max_posts 개만 처리(동기 호출 60s 회피). 0댓글 게시물은 호출 생략.
    """
    if account.platform not in COMMENTS_PLATFORMS:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"'{account.platform}' 는 댓글 수집을 지원하지 않습니다",
        )

    collector = await _build_collector(account)
    posts_result = await db.execute(
        select(SocialPost)
        .where(SocialPost.account_id == account.id)
        .order_by(SocialPost.posted_at.desc())
        .limit(max_posts)
    )
    posts = posts_result.scalars().all()

    # IG: permalink 만 저장된 게시물(external_id NULL)은 media_id 로 백필.
    # 이후 댓글/메트릭 수집이 숫자 ID 빠른 경로를 타고, 메트릭 수집도 정상화된다.
    # 인덱스 구축(1회) 실패는 전체를 막지 않도록 격리 — fetch_comments 가 내부 재해석.
    if account.platform == "instagram" and hasattr(collector, "resolve_media_ref"):
        for post in posts:
            if post.external_id or not post.url:
                continue
            try:
                media_id = await collector.resolve_media_ref(post.url)
            except CollectorError:
                break  # 토큰/권한 등 공통 실패 — 백필 중단(수집 단계에서 보고)
            except Exception:  # noqa: BLE001 — 개별 해석 실패는 건너뜀
                continue
            if media_id:
                post.external_id = media_id

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
        # 댓글 0개로 집계된 게시물은 Graph 호출 생략 (성능 — nginx 60s 타임아웃 회피).
        # 대량 계정에서 0댓글 게시물 네트워크 호출이 누적되면 동기 응답이 초과됨.
        if not post.comment_count:
            skipped += 1
            continue
        try:
            comments = await collector.fetch_comments(ref)
        except CollectorError as exc:
            failures.append(f"{ref}: {exc}")
            continue
        except Exception as exc:  # noqa: BLE001 — 개별 게시물 실패는 격리
            failures.append(f"{ref}: {exc}")
            continue
        for comment in comments:
            if not comment.get("external_id"):
                skipped += 1
                continue
            was_updated = await _upsert_comment(db, post.id, comment)
            if was_updated:
                updated += 1
            else:
                added += 1
        processed += 1

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"댓글 저장 실패: {exc}")

    return CollectCommentsResponse(
        posts_processed=processed,
        comments_added=added,
        comments_updated=updated,
        skipped=skipped,
        failures=failures,
    )


@router.post(
    "/accounts/{account_id}/collect-comments",
    response_model=CollectCommentsResponse,
    dependencies=[Depends(require_admin)],
)
async def collect_comments(
    account_id: str,
    db: AsyncSession = Depends(get_db),
):
    """단일 계정(소유/관리)의 모든 게시물 댓글 본문을 수집해 저장 (멱등)."""
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")
    return await _collect_comments_for_account(db, account)


@router.get(
    "/posts/{post_id}/comments",
    response_model=list[CommentRead],
)
async def list_post_comments(
    post_id: str,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """게시물의 댓글 목록 (오래된→최신)."""
    query = (
        select(SocialPostComment)
        .where(SocialPostComment.post_id == post_id)
        .order_by(SocialPostComment.commented_at.asc().nullslast())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/posts/{post_id}/comments/analyze",
    response_model=CommentAnalysisResponse,
)
async def analyze_post_comments(
    post_id: str,
    db: AsyncSession = Depends(get_db),
):
    """게시물에 수집된 댓글을 Claude 로 분석/요약 (한국어).

    먼저 댓글 수집이 되어 있어야 한다. ANTHROPIC_API_KEY 필요.
    """
    post = (
        await db.execute(select(SocialPost).where(SocialPost.id == post_id))
    ).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다")

    rows = await db.execute(
        select(SocialPostComment.text)
        .where(SocialPostComment.post_id == post_id)
        .order_by(SocialPostComment.commented_at.asc().nullslast())
    )
    comments = [r[0] for r in rows.all() if r[0] and r[0].strip()]
    if not comments:
        raise HTTPException(
            status_code=400,
            detail="이 게시물에 수집된 댓글이 없습니다. 먼저 '댓글 수집'을 실행하세요.",
        )
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503, detail="ANTHROPIC_API_KEY 미설정 — 댓글 분석 불가."
        )

    from app.services.sns_collectors.comment_analyzer import analyze_comments

    try:
        summary = await analyze_comments(
            post_title=post.title or "",
            comments=comments,
            comment_count=len(comments),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — 외부 LLM 호출 실패 격리
        raise HTTPException(status_code=502, detail=f"댓글 분석 실패: {type(exc).__name__}")

    return CommentAnalysisResponse(
        post_id=post.id, comment_count=len(comments), summary=summary
    )


@router.post(
    "/posts/{post_id}/comments/translate",
    response_model=CommentTranslateResponse,
)
async def translate_post_comments(
    post_id: str,
    force: bool = Query(False, description="True면 이미 번역된 댓글도 다시 번역"),
    db: AsyncSession = Depends(get_db),
):
    """게시물 댓글을 한국어로 번역(다국어→한국어). 원문은 보존, 번역문만 캐시.

    글로벌 채널 특성상 댓글이 외국어로 달리므로 마케팅 담당자가 읽을 수 있게 번역한다.
    이미 번역된 댓글은 건너뛴다(force=True면 재번역). ANTHROPIC_API_KEY 필요.
    """
    post = (
        await db.execute(select(SocialPost).where(SocialPost.id == post_id))
    ).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다")
    post_pk = post.id

    rows = await db.execute(
        select(SocialPostComment)
        .where(SocialPostComment.post_id == post_id)
        .order_by(SocialPostComment.commented_at.asc().nullslast())
    )
    all_comments = list(rows.scalars().all())

    # 번역 대상: 원문이 있고, force 거나 아직 미번역인 댓글.
    targets = [
        c
        for c in all_comments
        if (c.text and c.text.strip()) and (force or not c.translated_text)
    ]

    translated_count = 0
    if targets:
        if not settings.anthropic_api_key:
            raise HTTPException(
                status_code=503, detail="ANTHROPIC_API_KEY 미설정 — 댓글 번역 불가."
            )
        from app.services.sns_collectors.comment_translator import translate_to_korean

        try:
            results = await translate_to_korean([c.text or "" for c in targets])
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except Exception as exc:  # noqa: BLE001 — 외부 LLM 호출 실패 격리
            raise HTTPException(
                status_code=502, detail=f"댓글 번역 실패: {type(exc).__name__}"
            )
        for comment, translated in zip(targets, results):
            if translated:
                comment.translated_text = translated
                translated_count += 1
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"번역 저장 실패: {exc}")

    # 번역 반영된 최종 목록 재조회 (commit 후 일관 상태로 반환).
    final = await db.execute(
        select(SocialPostComment)
        .where(SocialPostComment.post_id == post_id)
        .order_by(SocialPostComment.commented_at.asc().nullslast())
    )
    return CommentTranslateResponse(
        post_id=post_pk,
        translated=translated_count,
        comments=list(final.scalars().all()),
    )


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


# ---------------- 전체 갱신 (사용자 트리거) ----------------


async def _refresh_one_account(
    db: AsyncSession,
    account: SocialAccount,
    period: str,
    include_metrics: bool,
) -> RefreshAccountResult:
    """계정 1개 갱신 — 게시물/팔로워 수집 + (옵션) 메트릭 수집. 실패는 격리.

    1) `_collect_for_account` 로 게시물·팔로워 스냅샷 수집(모든 플랫폼).
    2) include_metrics 면 fb/ig 한정 `_collect_metrics_for_account` 로 메트릭 수집.
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
        collected = await _collect_for_account(db, account)
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
            metrics = await _collect_metrics_for_account(
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
    dependencies=[Depends(require_admin)],
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
    """사용자(관리자)가 누르는 '전체 갱신' — 모든 활성 계정을 동기 일괄 수집.

    내부 cron 용 `/api/internal/sns/collect-all`(X-Internal-Token) 과 동일한 수집 로직
    (`_collect_for_account`, `_collect_metrics_for_account`)을 재사용하되, 일반 SNS 모듈
    권한(라우터 `require_module(MARKETING_SNS)`) + 관리자(`require_admin`)로 게이트한다.

    계정별 실패는 격리(`_refresh_one_account`)하고 계정 단위 성공/실패 요약을 반환한다.
    동기 처리: 계정 수가 소수(현재 3개 수준)이고 nginx /api/ 타임아웃이 300s 이므로
    동기로 충분. 계정·게시물이 크게 늘어 300s 초과가 우려되면 비동기 잡(설계 §2.3 안 A)으로
    전환한다(현재는 미적용).
    """
    if period not in VALID_PERIODS:
        raise HTTPException(status_code=422, detail="period 는 daily 또는 weekly 여야 합니다")

    accounts_q = await db.execute(
        select(SocialAccount).where(
            SocialAccount.is_active.is_(True),
            SocialAccount.platform.in_(SUPPORTED_PLATFORMS),
        )
    )
    accounts = accounts_q.scalars().all()

    results: list[RefreshAccountResult] = []
    for account in accounts:
        results.append(
            await _refresh_one_account(db, account, period, include_metrics)
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
            result = await _collect_comments_for_account(db, account)
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
