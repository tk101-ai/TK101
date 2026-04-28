from abc import ABC, abstractmethod
from datetime import date
from typing import TypedDict


class CollectedPost(TypedDict, total=False):
    posted_at: date
    title: str
    content_type: str  # "video" | "short"
    view_count: int | None
    like_count: int | None
    comment_count: int | None
    share_count: int | None
    url: str
    external_id: str
    extra_metadata: dict | None


class BaseCollector(ABC):
    @abstractmethod
    async def fetch_posts(self, since: date | None = None, until: date | None = None) -> list[CollectedPost]:
        ...

    @abstractmethod
    async def fetch_followers(self) -> int:
        ...
