"""IG permalink→media_id 해석 단위 테스트 (네트워크 없음).

- _instagram_shortcode: permalink/URL → shortcode 추출 (순수 함수).
- InstagramCollector.resolve_media_ref: 숫자 ID 직통 / shortcode 역매핑.

resolve_media_ref 는 미디어 인덱스를 미리 주입(_media_index_loaded=True)해
Graph 호출 없이 매핑만 검증한다. require_token() 우회를 위해 __new__ 로 인스턴스 생성.
"""
from __future__ import annotations

import pytest

from app.services.sns_collectors.instagram import (
    InstagramCollector,
    _instagram_shortcode,
    extract_instagram_media_id,
)


class TestInstagramShortcode:
    def test_post_permalink(self):
        assert (
            _instagram_shortcode("https://www.instagram.com/p/DXeGpNfGYSL/")
            == "DXeGpNfGYSL"
        )

    def test_reel_permalink(self):
        assert (
            _instagram_shortcode("https://www.instagram.com/reel/DXbMaYAkSOv/")
            == "DXbMaYAkSOv"
        )

    def test_tv_permalink(self):
        assert (
            _instagram_shortcode("https://instagram.com/tv/ABC123def/") == "ABC123def"
        )

    def test_no_trailing_slash(self):
        assert (
            _instagram_shortcode("https://www.instagram.com/p/DXeGpNfGYSL")
            == "DXeGpNfGYSL"
        )

    def test_non_instagram_url_is_none(self):
        assert _instagram_shortcode("https://example.com/p/abc/") is None

    def test_profile_url_without_shortcode_is_none(self):
        assert _instagram_shortcode("https://www.instagram.com/seoulcity/") is None

    def test_empty_is_none(self):
        assert _instagram_shortcode("") is None
        assert _instagram_shortcode(None) is None


def _collector_with_index(index: dict[str, str]) -> InstagramCollector:
    """require_token() 우회 — 인덱스 주입된 InstagramCollector."""
    c = InstagramCollector.__new__(InstagramCollector)
    c.user_ref = "17841400258176586"
    c._media_index_loaded = True
    c._shortcode_to_id = index
    return c


class TestResolveMediaRef:
    @pytest.mark.asyncio
    async def test_numeric_id_passthrough(self):
        c = _collector_with_index({})
        assert await c.resolve_media_ref("17912345678901234") == "17912345678901234"

    @pytest.mark.asyncio
    async def test_permalink_resolved_via_index(self):
        c = _collector_with_index({"DXeGpNfGYSL": "17999999999999999"})
        got = await c.resolve_media_ref(
            "https://www.instagram.com/p/DXeGpNfGYSL/"
        )
        assert got == "17999999999999999"

    @pytest.mark.asyncio
    async def test_permalink_not_in_index_is_none(self):
        c = _collector_with_index({"OTHER": "1"})
        got = await c.resolve_media_ref(
            "https://www.instagram.com/reel/UNKNOWN12345/"
        )
        assert got is None

    @pytest.mark.asyncio
    async def test_unrecognized_ref_is_none(self):
        c = _collector_with_index({})
        assert await c.resolve_media_ref("not-a-url-or-id") is None


class TestExtractMediaIdUnchanged:
    """기존 동작 회귀 방지 — 숫자/“igid_mediaid”는 그대로."""

    def test_numeric(self):
        assert extract_instagram_media_id("17912345678901234") == "17912345678901234"

    def test_shortcode_url_still_none_at_pure_layer(self):
        # 순수 함수는 shortcode 를 숫자 ID 로 못 바꿈 → resolve_media_ref 책임.
        assert (
            extract_instagram_media_id("https://www.instagram.com/p/DXeGpNfGYSL/")
            is None
        )
