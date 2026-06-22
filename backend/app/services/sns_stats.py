"""SNS 통계/집계 코어 (비 HTTP 로직).

라우터(`app.routers.sns`)에서 분리한 SQL 집계 + 피벗 빌딩:
- 주간 KPI (`stats_weekly`)
- 계정별 주차 게재건수 (`stats_weekly_posts`)
- 성장 카드 / 인기 게시물 / 트렌드 시계열
- 엑셀 내보내기용 데이터 집계(스냅샷 피벗 / 게시물 평면화 / 브랜드 통합 워크북)

동작은 기존 `sns.py` 와 **완전히 동일**하다(순수 이동). 라우터는 이 함수들을 호출해
스키마 객체를 받아 그대로 반환하거나 workbook 빌더로 넘긴다.
"""

import uuid
from datetime import date
from types import SimpleNamespace

from sqlalchemy import Integer, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sns import (
    SocialAccount,
    SocialPost,
    SocialWeeklySnapshot,
)
from app.schemas.sns import (
    GrowthCard,
    TopPost,
    TrendPoint,
    WeeklyKpiRow,
    WeeklyPostCountRow,
)
from app.services.sns_weeks import week_of_month_expr


async def compute_weekly_kpi(
    db: AsyncSession, *, year: int, month: int | None
) -> list[WeeklyKpiRow]:
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
    # week_of_month 을 snapshot 의 week_number(1~5)와 정렬(sns_weeks.week_of_month_expr).
    week_of_month = week_of_month_expr(SocialPost.posted_at)
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


async def compute_weekly_post_counts(
    db: AsyncSession, *, year: int, month: int
) -> list[WeeklyPostCountRow]:
    """계정(채널)별 주차별 게재건수 + 월 누적.

    주어진 (year, month)의 social_posts 를 계정 × 주차로 GROUP BY 한다.
    주차 = FLOOR((day-1)/7)+1 (week_of_month, 1~5) — compute_weekly_kpi 및
    sns_export._week_of_month 와 동일 공식(floor 월중 주차).
    각 계정 행은 week1~week5(주차별 건수) + total(월 합계)을 가진다.
    """
    week_of_month = week_of_month_expr(SocialPost.posted_at)

    q = (
        select(
            SocialAccount.id.label("account_id"),
            SocialAccount.platform.label("platform"),
            SocialAccount.language.label("language"),
            SocialAccount.handle.label("handle"),
            SocialAccount.client.label("client"),
            week_of_month,
            func.count(SocialPost.id).label("post_count"),
        )
        .join(SocialAccount, SocialAccount.id == SocialPost.account_id)
        .where(
            func.extract("year", SocialPost.posted_at) == year,
            func.extract("month", SocialPost.posted_at) == month,
        )
        .group_by(
            SocialAccount.id,
            SocialAccount.platform,
            SocialAccount.language,
            SocialAccount.handle,
            SocialAccount.client,
            week_of_month,
        )
    )
    result = await db.execute(q)

    # 계정별로 주차 건수를 누적 (한 계정이 여러 주차 행으로 나뉘어 나온다).
    by_account: dict[uuid.UUID, WeeklyPostCountRow] = {}
    for r in result.all():
        row = by_account.get(r.account_id)
        if row is None:
            row = WeeklyPostCountRow(
                account_id=r.account_id,
                platform=r.platform,
                language=r.language,
                handle=r.handle,
                client=r.client,
            )
            by_account[r.account_id] = row
        week = int(r.week_number)
        count = int(r.post_count)
        if 1 <= week <= 5:
            setattr(row, f"week{week}", getattr(row, f"week{week}") + count)
        row.total += count

    return sorted(
        by_account.values(),
        key=lambda x: (x.platform, x.language, x.handle or ""),
    )


async def compute_growth_cards(db: AsyncSession) -> list[GrowthCard]:
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
                handle=acc.handle,
                client=acc.client,
                current_followers=current,
                prev_followers=prev,
                growth_rate=growth_rate,
            )
        )
    return cards


async def compute_top_posts(
    db: AsyncSession,
    *,
    limit: int,
    language: str | None,
    platform: str | None,
) -> list[TopPost]:
    """반응(total_engagement) 상위 게시물."""
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


async def compute_trend(
    db: AsyncSession,
    *,
    language: str | None,
    platform: str | None,
    account_id: str | None,
    months: int,
) -> list[TrendPoint]:
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


# ---------------- 엑셀 내보내기용 데이터 집계 ----------------


async def collect_snapshots_export_rows(
    db: AsyncSession, *, year: int, month: int
) -> list[SimpleNamespace]:
    """주간 팔로워(계정별 1~5주차) 피벗 행.

    snapshots 쿼리(social_weekly_snapshots × social_accounts)를 재사용해
    계정별로 주차 팔로워 수를 피벗한다. 계정이 추가되면 자동 반영된다.
    """
    q = (
        select(
            SocialAccount.id.label("account_id"),
            SocialAccount.client.label("client"),
            SocialAccount.platform.label("platform"),
            SocialAccount.language.label("language"),
            SocialAccount.handle.label("handle"),
            SocialWeeklySnapshot.week_number.label("week_number"),
            SocialWeeklySnapshot.followers.label("followers"),
        )
        .join(SocialAccount, SocialAccount.id == SocialWeeklySnapshot.account_id)
        .where(
            SocialWeeklySnapshot.year == year,
            SocialWeeklySnapshot.month == month,
        )
    )
    result = await db.execute(q)

    # 계정별로 주차(1~5) 팔로워를 피벗.
    by_account: dict[uuid.UUID, SimpleNamespace] = {}
    for r in result.all():
        row = by_account.get(r.account_id)
        if row is None:
            row = SimpleNamespace(
                client=r.client,
                platform=r.platform,
                language=r.language,
                handle=r.handle,
                week1=None,
                week2=None,
                week3=None,
                week4=None,
                week5=None,
            )
            by_account[r.account_id] = row
        if 1 <= int(r.week_number) <= 5:
            setattr(row, f"week{int(r.week_number)}", r.followers)

    return sorted(
        by_account.values(),
        key=lambda x: (x.platform or "", x.language or "", x.handle or ""),
    )


async def collect_posts_export_rows(
    db: AsyncSession,
    *,
    account_id: str | None,
    date_from: date | None,
    date_to: date | None,
):
    """게시물 목록 평면화 행 (계정 식별 컬럼 JOIN).

    list_posts 와 동일한 필터(account_id/date_from/date_to)를 쓰되, 계정 식별
    컬럼(브랜드/플랫폼/어권/핸들)을 위해 social_accounts 를 JOIN 한다.
    """
    q = (
        select(
            SocialAccount.client.label("client"),
            SocialAccount.platform.label("platform"),
            SocialAccount.language.label("language"),
            SocialAccount.handle.label("handle"),
            SocialPost.posted_at.label("posted_at"),
            SocialPost.title.label("title"),
            SocialPost.content_type.label("content_type"),
            SocialPost.producer.label("producer"),
            SocialPost.view_count.label("view_count"),
            SocialPost.reach_count.label("reach_count"),
            SocialPost.comment_count.label("comment_count"),
            SocialPost.like_count.label("like_count"),
            SocialPost.share_count.label("share_count"),
            SocialPost.total_engagement.label("total_engagement"),
            SocialPost.url.label("url"),
        )
        .join(SocialAccount, SocialAccount.id == SocialPost.account_id)
        .order_by(SocialPost.posted_at.desc())
    )
    if account_id:
        q = q.where(SocialPost.account_id == account_id)
    if date_from:
        q = q.where(SocialPost.posted_at >= date_from)
    if date_to:
        q = q.where(SocialPost.posted_at <= date_to)
    result = await db.execute(q)
    return result.all()  # 각 Row 는 .client/.platform/... 으로 접근 가능.


async def collect_brand_workbook_data(
    db: AsyncSession, *, client: str, year: int, month: int
):
    """브랜드별 통합 워크북 입력 데이터 집계.

    반환: (accounts, summary_rows, posts_by_account, snapshots_by_account).
    완전 동적 — 주어진 client 의 계정을 DB 에서 순회하므로 특정 발주처/채널 하드코딩 없음.
    계정이 없으면 accounts 가 빈 리스트로 반환되며, 호출 측에서 404 처리한다.
    """
    # 1) 브랜드 계정.
    acc_result = await db.execute(
        select(SocialAccount)
        .where(SocialAccount.client == client)
        .order_by(SocialAccount.platform, SocialAccount.language)
    )
    accounts = acc_result.scalars().all()
    if not accounts:
        return [], [], {}, {}
    account_ids = [a.id for a in accounts]

    # 2) 계정별 주차 게재건수 (선택 월). sns_weeks.week_of_month_expr 단일 산식.
    week_of_month = week_of_month_expr(SocialPost.posted_at)
    counts_result = await db.execute(
        select(
            SocialPost.account_id.label("account_id"),
            week_of_month,
            func.count(SocialPost.id).label("post_count"),
            func.coalesce(func.sum(SocialPost.total_engagement), 0).label("interaction"),
        )
        .where(
            SocialPost.account_id.in_(account_ids),
            func.extract("year", SocialPost.posted_at) == year,
            func.extract("month", SocialPost.posted_at) == month,
        )
        .group_by(SocialPost.account_id, week_of_month)
    )
    summary_by_id: dict[uuid.UUID, WeeklyPostCountRow] = {}
    interaction_by_id: dict[uuid.UUID, int] = {}
    for r in counts_result.all():
        row = summary_by_id.get(r.account_id)
        if row is None:
            acc = next(a for a in accounts if a.id == r.account_id)
            row = WeeklyPostCountRow(
                account_id=r.account_id,
                platform=acc.platform,
                language=acc.language,
                handle=acc.handle,
                client=acc.client,
            )
            summary_by_id[r.account_id] = row
        week = int(r.week_number)
        if 1 <= week <= 5:
            setattr(row, f"week{week}", getattr(row, f"week{week}") + int(r.post_count))
        row.total += int(r.post_count)
        interaction_by_id[r.account_id] = interaction_by_id.get(r.account_id, 0) + int(r.interaction or 0)
    # interaction 을 summary 행에 부착(빌더가 getattr 로 읽음).
    summary_rows = []
    for acc_id, row in summary_by_id.items():
        summary_rows.append(
            SimpleNamespace(
                account_id=row.account_id,
                week1=row.week1, week2=row.week2, week3=row.week3,
                week4=row.week4, week5=row.week5, total=row.total,
                interaction=interaction_by_id.get(acc_id, 0),
            )
        )

    # 3) 계정별 주차 팔로워 (선택 월).
    snap_result = await db.execute(
        select(
            SocialWeeklySnapshot.account_id.label("account_id"),
            SocialWeeklySnapshot.week_number.label("week_number"),
            SocialWeeklySnapshot.followers.label("followers"),
        ).where(
            SocialWeeklySnapshot.account_id.in_(account_ids),
            SocialWeeklySnapshot.year == year,
            SocialWeeklySnapshot.month == month,
        )
    )
    snapshots_by_account: dict[uuid.UUID, dict[int, int]] = {}
    for r in snap_result.all():
        snapshots_by_account.setdefault(r.account_id, {})[int(r.week_number)] = r.followers

    # 4) 계정별 게시물 (선택 월, 배포일 오름차순 → 시트의 번호 순).
    posts_result = await db.execute(
        select(SocialPost)
        .where(
            SocialPost.account_id.in_(account_ids),
            func.extract("year", SocialPost.posted_at) == year,
            func.extract("month", SocialPost.posted_at) == month,
        )
        .order_by(SocialPost.posted_at.asc())
    )
    posts_by_account: dict[uuid.UUID, list[SocialPost]] = {}
    for post in posts_result.scalars().all():
        posts_by_account.setdefault(post.account_id, []).append(post)

    return accounts, summary_rows, posts_by_account, snapshots_by_account
