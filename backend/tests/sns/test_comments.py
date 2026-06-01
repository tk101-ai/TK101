"""Meta 댓글 파서 단위 테스트 — _build_comment (FB/IG).

네트워크 호출 없이 Graph 응답 dict → CollectedComment 매핑만 검증.
docker/CI 에서 실행 (httpx/pydantic 등 백엔드 deps 필요).
"""
from __future__ import annotations

from datetime import timezone

from app.services.sns_collectors.facebook import _build_comment as fb_build_comment
from app.services.sns_collectors.instagram import _build_comment as ig_build_comment


class TestInstagramCommentParser:
    def test_maps_core_fields(self):
        raw = {
            "id": "17890000000000000",
            "text": "정말 예쁘네요!",
            "username": "hong_gildong",
            "timestamp": "2026-05-01T09:30:00+0000",
            "like_count": 3,
        }
        c = ig_build_comment(raw)
        assert c is not None
        assert c["external_id"] == "17890000000000000"
        assert c["author"] == "hong_gildong"
        assert c["text"] == "정말 예쁘네요!"
        assert c["like_count"] == 3
        assert c["commented_at"].tzinfo is not None
        assert c["commented_at"].astimezone(timezone.utc).hour == 9

    def test_missing_id_returns_none(self):
        assert ig_build_comment({"text": "no id"}) is None

    def test_missing_text_becomes_empty_string(self):
        c = ig_build_comment({"id": "1", "username": "x"})
        assert c is not None
        assert c["text"] == ""

    def test_bad_timestamp_is_none(self):
        c = ig_build_comment({"id": "1", "timestamp": "not-a-date"})
        assert c is not None
        assert c["commented_at"] is None


class TestFacebookCommentParser:
    def test_maps_core_fields_with_from(self):
        raw = {
            "id": "12345_67890",
            "message": "좋은 정보 감사합니다",
            "created_time": "2026-04-20T01:00:00+0000",
            "like_count": 5,
            "from": {"id": "999", "name": "김철수"},
        }
        c = fb_build_comment(raw)
        assert c is not None
        assert c["external_id"] == "12345_67890"
        assert c["author"] == "김철수"
        assert c["text"] == "좋은 정보 감사합니다"
        assert c["like_count"] == 5
        assert c["commented_at"] is not None

    def test_missing_from_yields_none_author(self):
        # from 필드는 권한에 따라 비어 있을 수 있음 → author None 허용.
        c = fb_build_comment({"id": "1", "message": "hi"})
        assert c is not None
        assert c["author"] is None

    def test_from_not_dict_is_safe(self):
        c = fb_build_comment({"id": "1", "message": "hi", "from": "weird"})
        assert c is not None
        assert c["author"] is None

    def test_missing_id_returns_none(self):
        assert fb_build_comment({"message": "no id"}) is None
