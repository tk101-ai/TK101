"""Facebook Page 수집기 (Meta Graph API).

수집 항목:
- fetch_followers(): Page 팔로워 수 (followers_count, 없으면 fan_count).
- fetch_posts(): Page 게시물 목록 + 좋아요/댓글/공유/도달.
- fetch_post_metrics(post_ref): 단일 게시물(URL 또는 Graph ID)의 최신 메트릭.
  → FALLBACK 모드(수동 등록 콘텐츠)의 일/주 메트릭 자동저장에 사용.

토큰은 config(settings.meta_access_token)에서만 읽는다. 토큰이 없으면 meta_graph.require_token()
이 CollectorError(한국어 "메타 API 토큰 미설정") 를 던진다 — HTTP 501 이 아님.

라이브 검증 불가(토큰 부재): 토큰 주입 즉시 동작하도록 import-clean 하게 작성.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from app.services.sns_collectors.base import (
    BaseCollector,
    CollectedComment,
    CollectedPost,
    CollectorError,
    PostMetrics,
)
from app.services.sns_collectors.meta_graph import (
    graph_get,
    graph_get_paged,
    require_token,
    safe_int,
)

if TYPE_CHECKING:
    from app.models.sns import SocialAccount

# 게시물 1건에서 가져올 필드 (좋아요/댓글/공유는 summary 카운트만).
_POST_FIELDS = (
    "id,message,created_time,permalink_url,"
    "shares,"
    "likes.summary(true).limit(0),"
    "comments.summary(true).limit(0)"
)
# 도달은 insights 별도 엔드포인트로만 제공.
_REACH_METRIC = "post_impressions_unique"
# 댓글 노드 필드 — from(작성자)은 권한에 따라 비어 있을 수 있음.
_COMMENT_FIELDS = "id,message,created_time,like_count,from"


def extract_facebook_page_ref(*candidates: str | None) -> str | None:
    """계정 값들에서 Page 식별자(숫자 ID 또는 page slug)를 추출.

    우선순위: external_id(숫자) → URL 의 마지막 path segment → handle.
    """
    for raw in candidates:
        if not raw:
            continue
        text = raw.strip()
        if not text:
            continue
        if text.isdigit():
            return text
        if "facebook.com" in text:
            path = (urlparse(text).path or "").strip("/")
            if path:
                # facebook.com/<page>/... → 첫 segment
                segment = path.split("/")[0]
                if segment and segment not in {"profile.php"}:
                    return segment
            continue
        if not text.startswith("http"):
            return text.lstrip("@")
    return None


class FacebookCollector(BaseCollector):
    """Facebook Page 수집기."""

    def __init__(self, page_ref: str) -> None:
        require_token()  # 토큰 없으면 즉시 한국어 에러
        if not page_ref:
            raise CollectorError("Facebook Page ID/슬러그가 필요합니다.")
        self.page_ref = page_ref

    @classmethod
    async def from_account(cls, account: "SocialAccount") -> "FacebookCollector":
        page_ref = extract_facebook_page_ref(
            account.external_id, account.handle, account.page_url
        )
        if page_ref is None:
            raise ValueError(
                "Facebook Page ID 또는 페이지 URL/핸들이 필요합니다. 계정 정보에 입력해 주세요."
            )
        return cls(page_ref=page_ref)

    async def fetch_followers(self) -> int:
        data = await graph_get(
            self.page_ref, params={"fields": "followers_count,fan_count"}
        )
        followers = data.get("followers_count")
        if followers is None:
            followers = data.get("fan_count")
        return safe_int(followers) or 0

    async def fetch_posts(
        self,
        since: date | None = None,
        until: date | None = None,
    ) -> list[CollectedPost]:
        raw_posts = await graph_get_paged(
            f"{self.page_ref}/posts", params={"fields": _POST_FIELDS}
        )
        posts: list[CollectedPost] = []
        for raw in raw_posts:
            post = _build_post(raw)
            if post is None:
                continue
            if since is not None and post["posted_at"] < since:
                continue
            if until is not None and post["posted_at"] > until:
                continue
            posts.append(post)
        return posts

    async def fetch_post_metrics(self, post_ref: str) -> PostMetrics:
        post_id = extract_facebook_post_id(post_ref)
        if not post_id:
            raise CollectorError(f"Facebook 게시물 ID 를 인식하지 못했습니다: {post_ref}")
        data = await graph_get(post_id, params={"fields": _POST_FIELDS})
        reach = await self._fetch_reach(post_id)
        return _build_metrics(data, reach)

    async def fetch_comments(self, post_ref: str) -> list[CollectedComment]:
        """단일 게시물(URL 또는 Graph ID)의 댓글 본문 목록.

        소유/관리 페이지의 게시물에만 동작 (Graph API 제약).
        order=chronological 로 오래된→최신 순 수집.
        """
        post_id = extract_facebook_post_id(post_ref)
        if not post_id:
            raise CollectorError(f"Facebook 게시물 ID 를 인식하지 못했습니다: {post_ref}")
        raw_comments = await graph_get_paged(
            f"{post_id}/comments",
            params={"fields": _COMMENT_FIELDS, "order": "chronological"},
        )
        comments: list[CollectedComment] = []
        for raw in raw_comments:
            comment = _build_comment(raw)
            if comment is not None:
                comments.append(comment)
        return comments

    async def _fetch_reach(self, post_id: str) -> int | None:
        """post insights 에서 unique reach. 권한/가용성 따라 비어 있을 수 있음."""
        try:
            data = await graph_get(
                f"{post_id}/insights", params={"metric": _REACH_METRIC}
            )
        except CollectorError:
            return None
        for item in data.get("data") or []:
            values = item.get("values") or []
            if values:
                return safe_int(values[0].get("value"))
        return None


def extract_facebook_post_id(post_ref: str) -> str | None:
    """게시물 URL 또는 ID 문자열에서 Graph 게시물 ID 추출.

    - 이미 "<pageid>_<postid>" 또는 숫자형이면 그대로.
    - permalink URL 이면 ?story_fbid= 또는 path 의 숫자 토큰을 탐색.
    """
    if not post_ref:
        return None
    text = post_ref.strip()
    if "_" in text and all(part.isdigit() for part in text.split("_")):
        return text
    if text.isdigit():
        return text
    if "facebook.com" in text:
        from urllib.parse import parse_qs

        parsed = urlparse(text)
        qs = parse_qs(parsed.query)
        for key in ("story_fbid", "fbid", "id"):
            if key in qs and qs[key]:
                return qs[key][0]
        for segment in (parsed.path or "").split("/"):
            if segment.isdigit():
                return segment
    return None


def _parse_iso_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc).date()
    except ValueError:
        return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """ISO8601 → tz-aware UTC datetime. 댓글 작성시각 보존용."""
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except ValueError:
        return None


def _build_comment(raw: dict) -> CollectedComment | None:
    comment_id = raw.get("id")
    if not comment_id:
        return None
    author = None
    from_node = raw.get("from")
    if isinstance(from_node, dict):
        author = from_node.get("name")
    return CollectedComment(
        external_id=str(comment_id),
        author=author,
        text=raw.get("message") or "",
        commented_at=_parse_iso_datetime(raw.get("created_time")),
        like_count=safe_int(raw.get("like_count")),
        raw=raw,
    )


def _summary_count(node: dict | None) -> int | None:
    if not node:
        return None
    summary = node.get("summary") or {}
    return safe_int(summary.get("total_count"))


def _shares_count(node: dict | None) -> int | None:
    if not node:
        return None
    return safe_int(node.get("count"))


def _build_post(raw: dict) -> CollectedPost | None:
    post_id = raw.get("id")
    if not post_id:
        return None
    posted_at = _parse_iso_date(raw.get("created_time"))
    if posted_at is None:
        return None
    likes = _summary_count(raw.get("likes"))
    comments = _summary_count(raw.get("comments"))
    shares = _shares_count(raw.get("shares"))
    return CollectedPost(
        posted_at=posted_at,
        title=(raw.get("message") or "")[:500],
        content_type="post",
        view_count=None,
        reach_count=None,
        like_count=likes,
        comment_count=comments,
        share_count=shares,
        url=raw.get("permalink_url") or "",
        external_id=post_id,
        extra_metadata={"source": "facebook"},
    )


def _build_metrics(raw: dict, reach: int | None) -> PostMetrics:
    likes = _summary_count(raw.get("likes")) or 0
    comments = _summary_count(raw.get("comments")) or 0
    shares = _shares_count(raw.get("shares")) or 0
    return PostMetrics(
        views=None,
        reach=reach,
        likes=likes,
        comments=comments,
        shares=shares,
        engagement_total=likes + comments + shares,
        raw=raw,
    )
