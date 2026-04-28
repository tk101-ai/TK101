from sqlalchemy import Boolean, Column, Date, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from app.models.base import Base, TimestampMixin, UUIDMixin


class SocialAccount(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "social_accounts"

    platform = Column(String, nullable=False)
    language = Column(String, nullable=False)
    handle = Column(String, nullable=True)
    page_url = Column(String, nullable=True)
    external_id = Column(String, nullable=True)  # ex: YouTube channel ID
    is_active = Column(Boolean, default=True, nullable=False)
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
    extra_metadata = Column(JSONB, nullable=True)
