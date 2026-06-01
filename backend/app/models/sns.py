from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models.base import Base, TimestampMixin, UUIDMixin


class SocialAccount(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "social_accounts"

    platform = Column(String, nullable=False)
    language = Column(String, nullable=False)
    handle = Column(String, nullable=True)
    page_url = Column(String, nullable=True)
    external_id = Column(String, nullable=True)  # ex: YouTube channel ID, FB Page ID, IG Business ID
    is_active = Column(Boolean, default=True, nullable=False)
    # 클라이언트 구분 (예: 'seoul_city'). 향후 다른 발주처 채널 확장 대비. (마이그레이션 022)
    client = Column(String(32), nullable=True)
    extra_metadata = Column(JSONB, nullable=True)


class SocialWeeklySnapshot(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "social_weekly_snapshots"

    account_id = Column(UUID(as_uuid=True), ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    week_number = Column(Integer, nullable=False)
    followers = Column(Integer, nullable=False, default=0)
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SocialPost(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "social_posts"

    account_id = Column(UUID(as_uuid=True), ForeignKey("social_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    posted_at = Column(Date, nullable=False)
    title = Column(String, nullable=True)
    content_type = Column(String, nullable=True)
    producer = Column(String, nullable=True)
    view_count = Column(Integer, nullable=True)
    reach_count = Column(Integer, nullable=True)
    comment_count = Column(Integer, nullable=True)
    like_count = Column(Integer, nullable=True)
    share_count = Column(Integer, nullable=True)
    save_count = Column(Integer, nullable=True)
    repost_count = Column(Integer, nullable=True)
    total_engagement = Column(Integer, nullable=True)
    url = Column(String, nullable=True)
    data_recorded_at = Column(Date, nullable=True)
    external_id = Column(String, nullable=True, index=True)
    # 수동 등록 콘텐츠 여부 (FALLBACK 모드). True면 사용자가 배포일/제목/형태/URL 직접 입력. (마이그레이션 022)
    is_manual = Column(Boolean, default=False, nullable=False)
    extra_metadata = Column(JSONB, nullable=True)


class SocialPostMetricSnapshot(UUIDMixin, TimestampMixin, Base):
    """게시물별 시계열 메트릭 스냅샷 (마이그레이션 022).

    수동/자동 콘텐츠 모두 일/주 주기로 조회수·도달·좋아요·댓글·공유를 누적 기록한다.
    (post_id, period, captured_at::date) UNIQUE 로 같은 날·같은 주기엔 1건만 유지(멱등).
    """

    __tablename__ = "social_post_metric_snapshots"

    post_id = Column(
        UUID(as_uuid=True),
        ForeignKey("social_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    captured_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    period = Column(String(8), nullable=False)  # 'daily' | 'weekly'
    views = Column(BigInteger, nullable=True)
    reach = Column(BigInteger, nullable=True)
    likes = Column(BigInteger, nullable=True)
    comments = Column(BigInteger, nullable=True)
    shares = Column(BigInteger, nullable=True)
    engagement_total = Column(BigInteger, nullable=True)
    raw = Column(JSONB, nullable=True)


class SocialPostComment(UUIDMixin, TimestampMixin, Base):
    """게시물별 댓글 본문 (마이그레이션 026).

    소유/관리 페이지·IG 비즈니스 계정의 게시물 댓글만 수집한다(Graph API 제약).
    (post_id, external_comment_id) UNIQUE 로 재수집 시 멱등 upsert.
    """

    __tablename__ = "social_post_comments"

    post_id = Column(
        UUID(as_uuid=True),
        ForeignKey("social_posts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    external_comment_id = Column(String, nullable=True, index=True)  # Graph 댓글 ID
    author = Column(String, nullable=True)  # IG username / FB from.name
    text = Column(Text, nullable=True)
    commented_at = Column(DateTime(timezone=True), nullable=True)
    like_count = Column(Integer, nullable=True)
    raw = Column(JSONB, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "post_id", "external_comment_id", name="uq_post_comment_external"
        ),
    )
