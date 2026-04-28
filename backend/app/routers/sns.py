import io
import os
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import Integer, and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_internal_token, require_module
from app.models.sns import SocialAccount, SocialPost, SocialWeeklySnapshot
from app.schemas.sns import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    GrowthCard,
    ImportResponse,
    IngestRequest,
    IngestResponse,
    PostCreate,
    PostRead,
    PostUpdate,
    SnapshotCreate,
    SnapshotRead,
    TopPost,
    WeeklyKpiRow,
)

router = APIRouter(
    prefix="/api/sns",
    tags=["sns"],
    dependencies=[Depends(require_module("marketing_sns"))],
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


async def _collect_for_account(db: AsyncSession, account: SocialAccount) -> IngestResponse:
    """Run the appropriate collector for an account and persist results.

    Currently supports youtube only. The resolved channel_id is written back to
    account.external_id so subsequent calls skip handle resolution.
    """
    if account.platform != "youtube":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"'{account.platform}' 플랫폼 자동 수집은 아직 구현되지 않았습니다",
        )

    try:
        from app.services.sns_collectors.youtube import YouTubeCollector
    except ImportError as exc:
        raise HTTPException(status_code=500, detail=f"수집기 로딩 실패: {exc}")

    try:
        collector = await YouTubeCollector.from_account(account)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # Persist the resolved channel_id so we don't pay the resolution call next time.
    if account.external_id != collector.channel_id:
        account.external_id = collector.channel_id

    try:
        collected_posts = await collector.fetch_posts()
        followers = await collector.fetch_followers()
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
async def collect(account_id: str, db: AsyncSession = Depends(get_db)):
    """관리자가 단일 계정을 수동 트리거. SnsAccounts 페이지의 '지금 수집' 버튼이 사용."""
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")
    return await _collect_for_account(db, account)


# ---------------- 내부(시스템) 라우터 ----------------

internal_router = APIRouter(
    prefix="/api/internal/sns",
    tags=["sns-internal"],
    dependencies=[Depends(require_internal_token)],
)


@internal_router.post("/collect-all", response_model=IngestResponse)
async def collect_all_internal(db: AsyncSession = Depends(get_db)):
    """n8n 등 내부 시스템에서 호출. 자동 수집 가능한 모든 활성 계정 일괄 처리.

    현재는 platform=youtube 계정만 자동 수집 대상. 다른 플랫폼은 조용히 스킵.
    Collector 추가 시 SUPPORTED_PLATFORMS 확장.
    """
    SUPPORTED_PLATFORMS = ("youtube",)

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
