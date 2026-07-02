"""재편집 베이스 URL 만료 계산 단위 테스트 (StorageMode 회귀 방지).

#161 에서 StorageMode 기본을 Permanent 로 바꿨으나 앱 쪽 expires_at 이 무조건
now+7d 로 남아 재편집(i2i/i2v/v2v)이 7일 뒤 잘못 차단되던 버그를 고정한다.
Permanent 면 만료 없음(None), Temporary 면 텐센트 실제 만료(이미지 7d/영상 24h).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.routers.playground.media_gen import compute_media_expires_at

_NOW = datetime(2026, 7, 2, 12, 0, 0, tzinfo=timezone.utc)


def test_permanent_never_expires_image():
    assert compute_media_expires_at("Permanent", "image", _NOW) is None


def test_permanent_never_expires_video():
    assert compute_media_expires_at("Permanent", "video", _NOW) is None


def test_permanent_case_and_whitespace_insensitive():
    assert compute_media_expires_at("  permanent  ", "video", _NOW) is None


def test_temporary_image_expires_in_7d():
    assert compute_media_expires_at("Temporary", "image", _NOW) == _NOW + timedelta(days=7)


def test_temporary_video_expires_in_24h():
    assert compute_media_expires_at("Temporary", "video", _NOW) == _NOW + timedelta(hours=24)


def test_unknown_mode_treated_as_temporary():
    # 알 수 없는 값은 보수적으로 만료 있음(Temporary)로 처리.
    assert compute_media_expires_at("", "video", _NOW) == _NOW + timedelta(hours=24)
