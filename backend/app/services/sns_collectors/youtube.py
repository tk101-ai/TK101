"""YouTube Data API v3 collector.

Collects channel statistics (subscriber count) and recent uploads
(view/like/comment counts) for a given channel ID.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from app.config import settings
from app.services.sns_collectors.base import BaseCollector, CollectedPost

if TYPE_CHECKING:
    from app.models.sns import SocialAccount

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
HTTP_TIMEOUT_SECONDS = 15.0
MAX_PLAYLIST_ITEMS = 50

# YouTube channel IDs always start with "UC" and are 24 chars total.
_CHANNEL_ID_PATTERN = re.compile(r"^UC[A-Za-z0-9_-]{22}$")


def extract_youtube_handle(*candidates: str | None) -> str | None:
    """Pull a @handle out of any of the provided strings.

    Accepts raw handle ("SeoulCityOfficial"), @handle, or full URL like
    ``https://www.youtube.com/@SeoulCityOfficial``. Returns the handle
    without the leading @, or None if no candidate looked like a handle.
    """
    for raw in candidates:
        if not raw:
            continue
        text = raw.strip()
        if not text:
            continue
        if text.startswith("@"):
            return text[1:]
        if "youtube.com" in text or "youtu.be" in text:
            try:
                path = urlparse(text).path or ""
            except ValueError:
                continue
            for segment in path.split("/"):
                if segment.startswith("@"):
                    return segment[1:]
            # /channel/UC... case is handled by extract_youtube_channel_id
            continue
        if not text.startswith("http"):
            return text.lstrip("@")
    return None


def extract_youtube_channel_id(*candidates: str | None) -> str | None:
    """Pick a UC... channel ID out of any of the provided strings."""
    for raw in candidates:
        if not raw:
            continue
        text = raw.strip()
        if _CHANNEL_ID_PATTERN.match(text):
            return text
        if "youtube.com" in text:
            for segment in (urlparse(text).path or "").split("/"):
                if _CHANNEL_ID_PATTERN.match(segment):
                    return segment
    return None


class YouTubeCollector(BaseCollector):
    """Collector for YouTube channels using the Data API v3."""

    def __init__(self, channel_id: str, api_key: str | None = None) -> None:
        resolved_key = api_key or settings.google_youtube_api_key
        if not resolved_key:
            raise RuntimeError(
                "YouTube API key is not configured. "
                "Set GOOGLE_YOUTUBE_API_KEY or pass api_key explicitly."
            )
        self.channel_id = channel_id
        self._api_key = resolved_key

    @classmethod
    async def from_account(cls, account: "SocialAccount") -> "YouTubeCollector":
        """Build a collector from a SocialAccount row.

        Resolution order:
          1. account.external_id if it already looks like a channel ID.
          2. UC... channel ID embedded in handle / page_url.
          3. @handle from handle / page_url, resolved via channels?forHandle.

        Raises ValueError when no usable identifier is found.
        """
        channel_id = extract_youtube_channel_id(
            account.external_id, account.handle, account.page_url
        )
        if channel_id is None:
            handle = extract_youtube_handle(account.handle, account.page_url)
            if handle is None:
                raise ValueError(
                    "YouTube 채널 ID 또는 @핸들이 필요합니다. 계정의 외부 ID, 핸들, 또는 페이지 URL에 입력해 주세요."
                )
            resolved = await cls.resolve_handle(handle)
            if resolved is None:
                raise ValueError(f"YouTube 핸들 '@{handle}' 에 해당하는 채널을 찾지 못했습니다.")
            channel_id = resolved
        return cls(channel_id=channel_id)

    @classmethod
    async def resolve_handle(cls, handle: str, api_key: str | None = None) -> str | None:
        """Resolve a YouTube @handle to its UC... channel ID."""
        normalized = handle.lstrip("@").strip()
        if not normalized:
            return None
        resolved_key = api_key or settings.google_youtube_api_key
        if not resolved_key:
            raise RuntimeError("YouTube API key is not configured.")
        params = {
            "part": "id",
            "forHandle": f"@{normalized}",
            "key": resolved_key,
        }
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{YOUTUBE_API_BASE}/channels", params=params)
            response.raise_for_status()
            data = response.json()
        items = data.get("items") or []
        if not items:
            return None
        return items[0].get("id")

    async def fetch_followers(self) -> int:
        """Return the channel's subscriber count.

        Returns 0 if the channel has no items in the response.
        """
        params = {
            "part": "statistics",
            "id": self.channel_id,
            "key": self._api_key,
        }
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(f"{YOUTUBE_API_BASE}/channels", params=params)
            response.raise_for_status()
            data = response.json()

        items = data.get("items") or []
        if not items:
            return 0
        statistics = items[0].get("statistics") or {}
        subscriber_count = statistics.get("subscriberCount")
        if subscriber_count is None:
            return 0
        return int(subscriber_count)

    async def fetch_posts(
        self,
        since: date | None = None,
        until: date | None = None,
    ) -> list[CollectedPost]:
        """Fetch recent uploads for the channel.

        Workflow:
          1. Resolve the channel's uploads playlist via channels?part=contentDetails.
          2. Fetch up to MAX_PLAYLIST_ITEMS recent items from that playlist.
          3. Batch-fetch full statistics + snippet for those video IDs.
          4. Filter by [since, until] (inclusive) using publishedAt date.
        """
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            uploads_playlist_id = await self._resolve_uploads_playlist(client)
            if uploads_playlist_id is None:
                return []
            video_ids = await self._fetch_recent_video_ids(client, uploads_playlist_id)
            if not video_ids:
                return []
            videos = await self._fetch_video_details(client, video_ids)

        posts: list[CollectedPost] = []
        for video in videos:
            post = self._build_post(video)
            if post is None:
                continue
            if since is not None and post["posted_at"] < since:
                continue
            if until is not None and post["posted_at"] > until:
                continue
            posts.append(post)
        return posts

    async def _resolve_uploads_playlist(self, client: httpx.AsyncClient) -> str | None:
        params = {
            "part": "contentDetails",
            "id": self.channel_id,
            "key": self._api_key,
        }
        response = await client.get(f"{YOUTUBE_API_BASE}/channels", params=params)
        response.raise_for_status()
        data = response.json()
        items = data.get("items") or []
        if not items:
            return None
        content_details = items[0].get("contentDetails") or {}
        related = content_details.get("relatedPlaylists") or {}
        return related.get("uploads")

    async def _fetch_recent_video_ids(
        self,
        client: httpx.AsyncClient,
        playlist_id: str,
    ) -> list[str]:
        params = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": MAX_PLAYLIST_ITEMS,
            "key": self._api_key,
        }
        response = await client.get(f"{YOUTUBE_API_BASE}/playlistItems", params=params)
        response.raise_for_status()
        data = response.json()
        items = data.get("items") or []
        video_ids: list[str] = []
        for item in items:
            content_details = item.get("contentDetails") or {}
            video_id = content_details.get("videoId")
            if video_id:
                video_ids.append(video_id)
        return video_ids

    async def _fetch_video_details(
        self,
        client: httpx.AsyncClient,
        video_ids: list[str],
    ) -> list[dict]:
        params = {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids),
            "key": self._api_key,
        }
        response = await client.get(f"{YOUTUBE_API_BASE}/videos", params=params)
        response.raise_for_status()
        data = response.json()
        return data.get("items") or []

    @staticmethod
    def _build_post(video: dict) -> CollectedPost | None:
        video_id = video.get("id")
        snippet = video.get("snippet") or {}
        statistics = video.get("statistics") or {}
        if not video_id or not snippet:
            return None

        published_at_raw = snippet.get("publishedAt")
        posted_at = _parse_published_date(published_at_raw)
        if posted_at is None:
            return None

        title = snippet.get("title") or ""
        description = snippet.get("description") or ""
        content_type = _infer_content_type(description)
        url = (
            f"https://youtube.com/shorts/{video_id}"
            if content_type == "short"
            else f"https://www.youtube.com/watch?v={video_id}"
        )

        extra_metadata: dict = {"channel_title": snippet.get("channelTitle")}
        tags = snippet.get("tags")
        if tags:
            extra_metadata["tags"] = tags

        post: CollectedPost = {
            "posted_at": posted_at,
            "title": title,
            "content_type": content_type,
            "view_count": _safe_int(statistics.get("viewCount")),
            "like_count": _safe_int(statistics.get("likeCount")),
            "comment_count": _safe_int(statistics.get("commentCount")),
            "share_count": None,
            "url": url,
            "external_id": video_id,
            "extra_metadata": extra_metadata,
        }
        return post


def _parse_published_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        # YouTube returns ISO 8601 like "2024-04-01T12:00:00Z".
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc).date()
    except ValueError:
        return None


def _infer_content_type(description: str) -> str:
    if "#shorts" in description.lower():
        return "short"
    return "video"


def _safe_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
