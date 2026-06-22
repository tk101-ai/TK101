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
    # 댓글 AI 요약 캐시 (마이그레이션 034) — 프런트가 목록만으로 저장된 요약을 표시.
    comment_summary: str | None = None
    comment_summary_at: datetime | None = None

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


# ---------------- 콘텐츠 현황 (계정별 주간 게재건수) ----------------


class WeeklyPostCountRow(BaseModel):
    """계정(채널) 1개의 월간 주차별 게재건수 + 월 누적.

    week1~week5 = 해당 주차(주차=((day-1)//7)+1)에 게재된 게시물 수,
    total = 해당 월 전체 게재건수. 채널 식별을 위해 platform/language/handle/client 포함.
    """

    account_id: uuid.UUID
    platform: str
    language: str
    handle: str | None = None
    client: str | None = None
    week1: int = 0
    week2: int = 0
    week3: int = 0
    week4: int = 0
    week5: int = 0
    total: int = 0


class GrowthCard(BaseModel):
    language: str
    platform: str
    # 채널 식별축 — 브랜드(광고주)·핸들. 백필 전 기존 계정은 client=None.
    handle: str | None = None
    client: str | None = None
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


class TrendPoint(BaseModel):
    """팔로워 추이 한 점 — 채널(계정) × 주차."""

    account_id: uuid.UUID
    platform: str
    language: str
    handle: str | None = None
    year: int
    month: int
    week_number: int
    # 정렬·차트 X축용 라벨. 예: "2026-05-W3"
    period: str
    followers: int


class RefreshAccountResult(BaseModel):
    """전체 갱신 시 계정 1개의 처리 결과 (성공/실패 격리 단위)."""

    account_id: uuid.UUID
    platform: str
    language: str
    handle: str | None = None
    ok: bool
    # 게시물/팔로워 수집 단계 (모든 SUPPORTED_PLATFORMS).
    posts_added: int = 0
    posts_updated: int = 0
    snapshots_added: int = 0
    snapshots_updated: int = 0
    # 메트릭 수집 단계 (METRICS_PLATFORMS=fb/ig 만 해당).
    metrics_processed: int = 0
    # 실패/부분실패 사유 (한국어). 빈 배열이면 완전 성공.
    errors: list[str] = Field(default_factory=list)


class RefreshAllResponse(BaseModel):
    """전체 갱신 결과 요약 — 계정별 성공/실패 격리.

    `ok_count`/`failed_count` 는 계정 단위 집계. 게시물 수집은 성공했으나 메트릭만
    실패한 부분 실패는 그 계정을 ok=True 로 두되 사유를 `results[].errors` 에 남긴다.
    """

    ok_count: int
    failed_count: int
    total: int
    include_metrics: bool
    results: list[RefreshAccountResult] = Field(default_factory=list)


class AccountDeleteResponse(BaseModel):
    """계정 삭제 결과. hard=False면 소프트삭제(is_active=False), True면 영구 삭제."""

    id: uuid.UUID
    hard: bool
    deleted: bool  # True=행 영구 삭제, False=소프트삭제(보존)
    posts_deleted: int = 0
    snapshots_deleted: int = 0


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
    # 메트릭 수집 전 신규 게시물 동기화 결과 (fetch_posts 통합). 동기화 실패 시 0.
    posts_added: int = 0
    posts_updated: int = 0
    failures: list[str] = Field(default_factory=list)


# ---------------- 게시물 댓글 ----------------


class CommentRead(BaseModel):
    id: uuid.UUID
    post_id: uuid.UUID
    external_comment_id: str | None
    author: str | None
    text: str | None
    translated_text: str | None = None
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


class CommentTranslateResponse(BaseModel):
    """게시물 댓글 번역 결과 — 번역된 건수 + 번역 포함 전체 댓글."""

    post_id: uuid.UUID
    translated: int  # 이번 호출에서 새로 번역한 건수
    comments: list[CommentRead]


class CommentAnalysisResponse(BaseModel):
    """게시물 댓글 AI 분석/요약 결과."""

    post_id: uuid.UUID
    comment_count: int
    summary: str
    summary_at: datetime | None = None


# ---------------- Excel Import ----------------


class ImportResponse(BaseModel):
    accounts_added: int
    snapshots_added: int
    posts_added: int
    posts_updated: int
