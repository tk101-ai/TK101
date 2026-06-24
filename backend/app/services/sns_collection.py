"""SNS 수집 오케스트레이션 (비 HTTP 로직).

라우터(`app.routers.sns`)에서 분리한 수집 코어:
- DB upsert 헬퍼 (post / snapshot / metric snapshot / comment)
- 플랫폼별 수집기 빌드 (`_build_collector`)
- 계정 단위 수집/메트릭/댓글 오케스트레이션

동작은 기존 `sns.py` 와 **완전히 동일**하다(순수 이동). 일부 함수는 호출 측 라우터의
편의를 위해 의도적으로 `HTTPException` 을 던진다 — 기존 동작을 보존하기 위함.
"""

import logging
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sns import (
    SocialAccount,
    SocialPost,
    SocialPostComment,
    SocialPostMetricSnapshot,
    SocialWeeklySnapshot,
)
from app.schemas.sns import (
    CollectCommentsResponse,
    CollectMetricsResponse,
    IngestResponse,
    PostCreate,
    SnapshotCreate,
)
from app.services.sns_collectors.base import BaseCollector, CollectorError

logger = logging.getLogger("app.routers.sns")

# 자동 수집 가능한 플랫폼. Collector 추가 시 여기에 등록.
SUPPORTED_PLATFORMS = ("youtube", "facebook", "instagram")
# 메트릭 시계열(collect-metrics)을 지원하는 플랫폼.
# youtube: Data API videos.list?part=statistics (views/likes/comments). reach/shares 는 미제공.
METRICS_PLATFORMS = ("facebook", "instagram", "youtube")
# 댓글 본문(collect-comments)을 지원하는 플랫폼.
# fb/ig 는 소유/관리 계정 한정. youtube 는 commentThreads.list 로 공개 영상 댓글 수집(소유 무관).
COMMENTS_PLATFORMS = ("facebook", "instagram", "youtube")
VALID_PERIODS = ("daily", "weekly")

# 동기(대화형) 메트릭 수집 1회 처리 게시물 상한 — nginx 60s 타임아웃(504) 회피.
# 게시물당 2회 Graph 호출(post + insights)이라 댓글 수집보다 무겁다.
# 최근 게시물 우선. 전체 백필은 internal cron(max_posts=None)이 담당.
METRICS_MAX_POSTS_PER_RUN = 20

# 대화형 댓글 수집 1회 처리 게시물 상한 — nginx 60s 타임아웃 회피.
# 최근 게시물 우선. 전체 백필이 필요하면 cron 을 반복 호출(멱등).
COMMENTS_MAX_POSTS_PER_RUN = 25


# ---------------- DB upsert 헬퍼 ----------------


async def upsert_snapshot(
    db: AsyncSession, payload: SnapshotCreate
) -> tuple[SocialWeeklySnapshot, bool]:
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


async def upsert_post(db: AsyncSession, payload: PostCreate) -> bool:
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


# ---------------- 자동 수집 트리거 ----------------


def current_iso_week_parts(today: date | None = None) -> tuple[int, int, int]:
    """Return (year, month, week_of_month) where week_of_month uses 1-5 scheme matching snapshots."""
    today = today or date.today()
    week_of_month = ((today.day - 1) // 7) + 1
    return today.year, today.month, week_of_month


async def build_collector(account: SocialAccount) -> BaseCollector:
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
        logger.exception("SNS 수집기 로딩 실패")
        raise HTTPException(
            status_code=500, detail=f"수집기 로딩 실패: {type(exc).__name__}"
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except CollectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


async def collect_for_account(
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
    collector = await build_collector(account)

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
        logger.exception("SNS 외부 API 호출 실패")
        raise HTTPException(
            status_code=502, detail=f"외부 API 호출 실패: {type(exc).__name__}"
        )

    posts_added = 0
    posts_updated = 0
    snapshots_added = 0
    snapshots_updated = 0

    try:
        for cp in collected_posts:
            payload = PostCreate(account_id=account.id, **cp)
            updated = await upsert_post(db, payload)
            if updated:
                posts_updated += 1
            else:
                posts_added += 1

        year, month, week_number = current_iso_week_parts()
        snap_payload = SnapshotCreate(
            account_id=account.id,
            year=year,
            month=month,
            week_number=week_number,
            followers=int(followers),
        )
        _, was_updated = await upsert_snapshot(db, snap_payload)
        if was_updated:
            snapshots_updated += 1
        else:
            snapshots_added += 1

        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("SNS 수집 데이터 저장 실패")
        raise HTTPException(
            status_code=500, detail=f"수집 데이터 저장 실패: {type(exc).__name__}"
        )

    return IngestResponse(
        posts_added=posts_added,
        posts_updated=posts_updated,
        snapshots_added=snapshots_added,
        snapshots_updated=snapshots_updated,
    )


# ---------------- 게시물 메트릭 시계열 (collect-metrics) ----------------


def post_ref(post: SocialPost) -> str | None:
    """수집기에 넘길 게시물 참조값. external_id 우선, 없으면 URL."""
    return post.external_id or post.url


def writeback_post_metrics(post: SocialPost, metrics) -> None:
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


async def sync_account_posts(
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
        if await upsert_post(db, payload):
            updated += 1
        else:
            added += 1
    try:
        followers = await collector.fetch_followers()
        year, month, week_number = current_iso_week_parts()
        await upsert_snapshot(
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


async def upsert_metric_snapshot(
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


async def collect_metrics_for_account(
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

    collector = await build_collector(account)

    # 1) 신규 게시물 동기화 — '메트릭 수집' 한 번으로 최근 게시물도 갱신되게 한다.
    #    동기화 실패(권한/네트워크)는 기존 게시물 메트릭 수집을 막지 않도록 격리한다.
    posts_added = 0
    posts_updated = 0
    sync_failures: list[str] = []
    try:
        posts_added, posts_updated = await sync_account_posts(db, account, collector)
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
        ref = post_ref(post)
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
        was_updated = await upsert_metric_snapshot(db, post.id, period, metrics)
        writeback_post_metrics(post, metrics)
        processed += 1
        if was_updated:
            updated += 1
        else:
            added += 1

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("SNS 메트릭 저장 실패")
        raise HTTPException(
            status_code=500, detail=f"메트릭 저장 실패: {type(exc).__name__}"
        )

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


# ---------------- 게시물 댓글 (collect-comments) ----------------


async def upsert_comment(db: AsyncSession, post_id, comment) -> bool:
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


async def collect_comments_for_account(
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

    collector = await build_collector(account)
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
        ref = post_ref(post)
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
            was_updated = await upsert_comment(db, post.id, comment)
            if was_updated:
                updated += 1
            else:
                added += 1
        processed += 1

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        logger.exception("SNS 댓글 저장 실패")
        raise HTTPException(
            status_code=500, detail=f"댓글 저장 실패: {type(exc).__name__}"
        )

    return CollectCommentsResponse(
        posts_processed=processed,
        comments_added=added,
        comments_updated=updated,
        skipped=skipped,
        failures=failures,
    )
