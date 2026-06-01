import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class Platform(str, Enum):
    FACEBOOK = "facebook"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    YOUTUBE = "youtube"
    WEIBO = "weibo"


class Language(str, Enum):
    EN = "en"
    ZH = "zh"
    JA = "ja"


# ---------------- Account ----------------


class AccountCreate(BaseModel):
    platform: Platform
    language: Language
    handle: str | None = None
    page_url: str | None = None
    external_id: str | None = None
    is_active: bool = True
    client: str | None = None
    extra_metadata: dict[str, Any] | None = None


class AccountUpdate(BaseModel):
    platform: Platform | None = None
    language: Language | None = None
    handle: str | None = None
    page_url: str | None = None
    external_id: str | None = None
    is_active: bool | None = None
    client: str | None = None
    extra_metadata: dict[str, Any] | None = None


class AccountRead(BaseModel):
    id: uuid.UUID
    platform: str
    language: str
    handle: str | None
    page_url: str | None
    external_id: str | None
    is_active: bool
    client: str | None = None
    extra_metadata: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------- Snapshot ----------------


class SnapshotCreate(BaseModel):
    account_id: uuid.UUID
    year: int
    month: int = Field(ge=1, le=12)
    week_number: int = Field(ge=1, le=5)
    followers: int = Field(ge=0)


class SnapshotRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    year: int
    month: int
    week_number: int
    followers: int
    captured_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------- Post ----------------


class PostCreate(BaseModel):
    account_id: uuid.UUID
    posted_at: date
    title: str | None = None
    content_type: str | None = None
    producer: str | None = None
    view_count: int | None = None
    reach_count: int | None = None
    comment_count: int | None = None
    like_count: int | None = None
    share_count: int | None = None
    save_count: int | None = None
    repost_count: int | None = None
    total_engagement: int | None = None
    url: str | None = None
    data_recorded_at: date | None = None
    external_id: str | None = None
    extra_metadata: dict[str, Any] | None = None


class PostUpdate(BaseModel):
    posted_at: date | None = None
    title: str | None = None
    content_type: str | None = None
    producer: str | None = None
    view_count: int | None = None
    reach_count: int | None = None
    comment_count: int | None = None
    like_count: int | None = None
    share_count: int | None = None
    save_count: int | None = None
    repost_count: int | None = None
    total_engagement: int | None = None
    url: str | None = None
    data_recorded_at: date | None = None
    external_id: str | None = None
    extra_metadata: dict[str, Any] | None = None


class PostRead(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    posted_at: date
    title: str | None
    content_type: str | None
    producer: str | None
    view_count: int | None
    reach_count: int | None
    comment_count: int | None
    like_count: int | None
    share_count: int | None
    save_count: int | None
    repost_count: int | None
    total_engagement: int | None
    url: str | None
    data_recorded_at: date | None
    external_id: str | None
    is_manual: bool = False
    extra_metadata: dict[str, Any] | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------- Ingest ----------------


class IngestRequest(BaseModel):
    source: str
    posts: list[PostCreate] = Field(default_factory=list)
    snapshots: list[SnapshotCreate] = Field(default_factory=list)


class IngestResponse(BaseModel):
    posts_added: int
    posts_updated: int
    snapshots_added: int
    snapshots_updated: int


# ---------------- Stats / Widgets ----------------


class WeeklyKpiRow(BaseModel):
    language: str
    platform: str
    year: int
    month: int
    week_number: int
    followers: int
    post_count: int
    view_count: int
    reaction_count: int


class GrowthCard(BaseModel):
    language: str
    platform: str
    current_followers: int
    prev_followers: int
    growth_rate: float


class TopPost(BaseModel):
    id: uuid.UUID
    posted_at: date
    title: str | None
    language: str
    platform: str
    view_count: int | None
    total_engagement: int | None
    url: str | None


# ---------------- 수동 콘텐츠 등록 (FALLBACK 모드) ----------------


class ContentCreate(BaseModel):
    """수동 콘텐츠 등록 — 배포일/제목/형태(제작주체)/URL. (메타 토큰 없어도 동작)"""

    posted_at: date
    title: str | None = None
    content_type: str | None = None  # 형태: post/reel/image 등
    producer: str | None = None  # 제작주체: 서울제작/TK제작 등
    url: str | None = None
    external_id: str | None = None


# ---------------- 게시물 메트릭 스냅샷 (시계열) ----------------


class MetricSnapshotRead(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    captured_at: datetime
    period: str
    views: int | None
    reach: int | None
    likes: int | None
    comments: int | None
    shares: int | None
    engagement_total: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CollectMetricsResponse(BaseModel):
    period: str
    posts_processed: int
    snapshots_added: int
    snapshots_updated: int
    skipped: int
    failures: list[str] = Field(default_factory=list)


# ---------------- 게시물 댓글 ----------------


class CommentRead(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    external_comment_id: str | None
    author: str | None
    text: str | None
    commented_at: datetime | None
    like_count: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class CollectCommentsResponse(BaseModel):
    posts_processed: int
    comments_added: int
    comments_updated: int
    skipped: int
    failures: list[str] = Field(default_factory=list)


class CommentAnalysisResponse(BaseModel):
    """게시물 댓글 AI 분석/요약 결과."""

    post_id: uuid.UUID
    comment_count: int
    summary: str


# ---------------- Excel Import ----------------


class ImportResponse(BaseModel):
    accounts_added: int
    snapshots_added: int
    posts_added: int
    posts_updated: int
