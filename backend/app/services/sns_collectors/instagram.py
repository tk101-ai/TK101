"""Instagram Business 수집기 (Meta Graph API).

전제: IG 프로페셔널(비즈니스/크리에이터) 계정이 Facebook Page 에 연결돼 있어야 한다.
external_id 에 IG Business Account ID(숫자)를 저장하는 것을 권장.

수집 항목:
- fetch_followers(): IG followers_count.
- fetch_posts(): media 목록 + 좋아요/댓글 (조회/도달은 insights).
- fetch_post_metrics(post_ref): 단일 media(URL 또는 media ID)의 좋아요/댓글 + insights(reach/views).
  → FALLBACK 모드(수동 등록 콘텐츠)의 일/주 메트릭 자동저장에 사용.

토큰은 config(settings.meta_access_token)에서만 읽는다. 토큰이 없으면 CollectorError(한국어).
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

# media 노드 기본 필드.
_MEDIA_FIELDS = (
    "id,caption,media_type,permalink,timestamp,"
    "like_count,comments_count"
)
# media insights — v25부터 impressions/plays 가 deprecated 되고 'views' 로 통합됨.
# 일반 게시물·reels 모두 reach,views 로 요청한다(구버전 metric 요청 시 Graph 오류 → 빈 결과).
_MEDIA_INSIGHT_METRICS = "reach,views"
_REELS_INSIGHT_METRICS = "reach,views"
# 댓글 노드 필드 — IG 댓글은 text/username/timestamp/like_count.
_COMMENT_FIELDS = "id,text,username,timestamp,like_count"
# permalink→media_id 매핑용 미디어 인덱스 페이지 상한 (id/permalink 만이라 가벼움).
_MEDIA_INDEX_MAX_PAGES = 50
# permalink 경로에서 shortcode 앞에 오는 segment.
_SHORTCODE_PREFIXES = {"p", "reel", "reels", "tv"}


def extract_instagram_user_ref(*candidates: str | None) -> str | None:
    """계정 값들에서 IG Business 식별자(숫자 ID 또는 username) 추출."""
    for raw in candidates:
        if not raw:
            continue
        text = raw.strip()
        if not text:
            continue
        if text.isdigit():
            return text
        if "instagram.com" in text:
            path = (urlparse(text).path or "").strip("/")
            if path:
                segment = path.split("/")[0]
                if segment:
                    return segment.lstrip("@")
            continue
        if not text.startswith("http"):
            return text.lstrip("@")
    return None


class InstagramCollector(BaseCollector):
    """Instagram Business 수집기."""

    def __init__(self, user_ref: str) -> None:
        require_token()
        if not user_ref:
            raise CollectorError("Instagram Business 계정 ID 가 필요합니다.")
        self.user_ref = user_ref
        # shortcode→media_id 인덱스 lazy 캐시 (permalink 만 저장된 게시물 해석용).
        self._media_index_loaded = False
        self._shortcode_to_id: dict[str, str] = {}

    @classmethod
    async def from_account(cls, account: "SocialAccount") -> "InstagramCollector":
        user_ref = extract_instagram_user_ref(
            account.external_id, account.handle, account.page_url
        )
        if user_ref is None:
            raise ValueError(
                "Instagram Business 계정 ID(숫자) 또는 프로필 URL/핸들이 필요합니다. "
                "계정 정보에 입력해 주세요."
            )
        return cls(user_ref=user_ref)

    async def _load_media_index(self) -> dict[str, str]:
        """계정 미디어 목록에서 shortcode→media_id 인덱스 구축 (1회, 캐시).

        permalink 만 저장된 게시물(external_id NULL)의 댓글/메트릭 수집을 위해,
        본인 소유 계정의 /{user}/media?fields=id,permalink 로 매핑을 만든다.
        """
        if self._media_index_loaded:
            return self._shortcode_to_id
        self._media_index_loaded = True
        raw_media = await graph_get_paged(
            f"{self.user_ref}/media",
            params={"fields": "id,permalink"},
            max_pages=_MEDIA_INDEX_MAX_PAGES,
        )
        index: dict[str, str] = {}
        for media in raw_media:
            media_id = media.get("id")
            shortcode = _instagram_shortcode(media.get("permalink"))
            if media_id and shortcode:
                index[shortcode] = str(media_id)
        self._shortcode_to_id = index
        return index

    async def resolve_media_ref(self, post_ref: str | None) -> str | None:
        """게시물 참조(숫자 ID/permalink/URL)를 Graph media_id 로 해석.

        숫자 media_id 면 그대로. permalink shortcode 면 미디어 인덱스로 역매핑.
        해석 실패 시 None (caller 가 skip 처리).
        """
        direct = extract_instagram_media_id(post_ref)
        if direct:
            return direct
        shortcode = _instagram_shortcode(post_ref)
        if shortcode:
            index = await self._load_media_index()
            return index.get(shortcode)
        return None

    async def fetch_followers(self) -> int:
        data = await graph_get(
            self.user_ref, params={"fields": "followers_count"}
        )
        return safe_int(data.get("followers_count")) or 0

    async def fetch_posts(
        self,
        since: date | None = None,
        until: date | None = None,
    ) -> list[CollectedPost]:
        raw_media = await graph_get_paged(
            f"{self.user_ref}/media", params={"fields": _MEDIA_FIELDS}
        )
        posts: list[CollectedPost] = []
        for raw in raw_media:
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
        media_id = await self.resolve_media_ref(post_ref)
        if not media_id:
            raise CollectorError(f"Instagram 미디어 ID 를 인식하지 못했습니다: {post_ref}")
        data = await graph_get(media_id, params={"fields": _MEDIA_FIELDS})
        insights = await self._fetch_insights(data)
        return _build_metrics(data, insights)

    async def fetch_comments(self, post_ref: str) -> list[CollectedComment]:
        """단일 media(URL 또는 media ID)의 댓글 본문 목록.

        소유/관리 IG 비즈니스 계정의 미디어에만 동작 (Graph API 제약).
        external_id(숫자) 가 없고 permalink 만 있는 게시물도 미디어 인덱스로 해석한다.
        """
        media_id = await self.resolve_media_ref(post_ref)
        if not media_id:
            raise CollectorError(f"Instagram 미디어 ID 를 인식하지 못했습니다: {post_ref}")
        raw_comments = await graph_get_paged(
            f"{media_id}/comments", params={"fields": _COMMENT_FIELDS}
        )
        comments: list[CollectedComment] = []
        for raw in raw_comments:
            comment = _build_comment(raw)
            if comment is not None:
                comments.append(comment)
        return comments

    async def _fetch_insights(self, media: dict) -> dict[str, int | None]:
        """media insights(reach/views). 미디어 타입에 따라 metric 선택, 실패 시 빈 dict."""
        media_id = media.get("id")
        if not media_id:
            return {}
        is_reel = (media.get("media_type") or "").upper() in {"VIDEO", "REELS"}
        metrics = _REELS_INSIGHT_METRICS if is_reel else _MEDIA_INSIGHT_METRICS
        try:
            data = await graph_get(
                f"{media_id}/insights", params={"metric": metrics}
            )
        except CollectorError:
            return {}
        result: dict[str, int | None] = {}
        for item in data.get("data") or []:
            name = item.get("name")
            values = item.get("values") or []
            if name and values:
                result[name] = safe_int(values[0].get("value"))
        return result


def _instagram_shortcode(url_or_ref: str | None) -> str | None:
    """IG permalink/URL 에서 shortcode 추출.

    `https://www.instagram.com/p/DXeGpNfGYSL/` → `DXeGpNfGYSL`
    `/reel/DXbMaYAkSOv/` → `DXbMaYAkSOv`. /p/, /reel(s)/, /tv/ 뒤 segment.
    instagram.com 이 아니거나 패턴 불일치면 None.
    """
    if not url_or_ref:
        return None
    text = url_or_ref.strip()
    if "instagram.com" not in text:
        return None
    segments = [seg for seg in (urlparse(text).path or "").split("/") if seg]
    for idx, seg in enumerate(segments):
        if seg in _SHORTCODE_PREFIXES and idx + 1 < len(segments):
            return segments[idx + 1]
    return None


def extract_instagram_media_id(post_ref: str) -> str | None:
    """media URL 또는 ID 문자열에서 Graph media ID 추출.

    permalink 의 shortcode 만으로는 Graph media id 를 직접 얻을 수 없으므로,
    숫자 media id 가 들어오면 그대로 쓰고, URL 이면 마지막 숫자 segment 를 시도한다.
    실무에선 fetch_posts 가 저장한 external_id(media id)를 post_ref 로 넘기는 것을 권장.
    """
    if not post_ref:
        return None
    text = post_ref.strip()
    if text.isdigit():
        return text
    if "instagram.com" in text:
        for segment in (urlparse(text).path or "").split("/"):
            if segment.isdigit():
                return segment
    # "<igid>_<mediaid>" 형태도 허용.
    if "_" in text and all(part.isdigit() for part in text.split("_")):
        return text
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
    """ISO8601 → tz-aware UTC datetime. 댓글 작성시각 보존용(날짜만이 아닌 시각까지)."""
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
    return CollectedComment(
        external_id=str(comment_id),
        author=raw.get("username"),
        text=raw.get("text") or "",
        commented_at=_parse_iso_datetime(raw.get("timestamp")),
        like_count=safe_int(raw.get("like_count")),
        raw=raw,
    )


def _media_content_type(media_type: str | None) -> str:
    upper = (media_type or "").upper()
    if upper in {"VIDEO", "REELS"}:
        return "reel"
    if upper == "CAROUSEL_ALBUM":
        return "post"
    return "image"


def _build_post(raw: dict) -> CollectedPost | None:
    media_id = raw.get("id")
    if not media_id:
        return None
    posted_at = _parse_iso_date(raw.get("timestamp"))
    if posted_at is None:
        return None
    return CollectedPost(
        posted_at=posted_at,
        title=(raw.get("caption") or "")[:500],
        content_type=_media_content_type(raw.get("media_type")),
        view_count=None,
        reach_count=None,
        like_count=safe_int(raw.get("like_count")),
        comment_count=safe_int(raw.get("comments_count")),
        share_count=None,
        url=raw.get("permalink") or "",
        external_id=media_id,
        extra_metadata={"source": "instagram", "media_type": raw.get("media_type")},
    )


def _build_metrics(raw: dict, insights: dict[str, int | None]) -> PostMetrics:
    likes = safe_int(raw.get("like_count")) or 0
    comments = safe_int(raw.get("comments_count")) or 0
    reach = insights.get("reach")
    # v25 'views' 우선, 구버전 metric(plays/impressions)도 폴백 처리.
    views = (
        insights.get("views")
        or insights.get("plays")
        or insights.get("impressions")
    )
    return PostMetrics(
        views=views,
        reach=reach,
        likes=likes,
        comments=comments,
        shares=None,
        engagement_total=likes + comments,
        raw={"media": raw, "insights": insights},
    )
