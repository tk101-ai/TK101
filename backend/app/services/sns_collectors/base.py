from abc import ABC, abstractmethod
from datetime import date
from typing import TypedDict


class CollectedPost(TypedDict, total=False):
    posted_at: date
    title: str
    content_type: str  # "video" | "short" | "post" | "reel" | "image"
    view_count: int | None
    reach_count: int | None
    like_count: int | None
    comment_count: int | None
    share_count: int | None
    url: str
    external_id: str
    extra_metadata: dict | None


class PostMetrics(TypedDict, total=False):
    """단일 게시물의 메트릭 스냅샷 (FALLBACK 모드 collect-metrics 용)."""

    views: int | None
    reach: int | None
    likes: int | None
    comments: int | None
    shares: int | None
    engagement_total: int | None
    raw: dict | None


class CollectorError(RuntimeError):
    """수집기 공통 에러 — 사용자 노출용 한국어 메시지를 담는다.

    토큰 미설정/권한 부족 등 운영자가 조치 가능한 상황에 사용한다.
    라우터는 이 메시지를 그대로 503 detail 로 내려 UI 가 표시한다.
    """


class BaseCollector(ABC):
    @abstractmethod
    async def fetch_posts(self, since: date | None = None, until: date | None = None) -> list[CollectedPost]:
        ...

    @abstractmethod
    async def fetch_followers(self) -> int:
        ...

    async def fetch_post_metrics(self, post_ref: str) -> PostMetrics:
        """알려진 게시물(URL 또는 외부 ID)의 최신 메트릭을 조회.

        기본 구현은 미지원 표시. 메트릭을 지원하는 수집기(Meta 등)가 오버라이드한다.
        """
        raise CollectorError(
            f"{type(self).__name__} 는 게시물 메트릭 수집을 지원하지 않습니다."
        )
