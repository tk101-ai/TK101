"""query_multilingual 단위 테스트 — 다국어 쿼리 확장 회귀 방지.

LLM 호출(call_claude)은 mocking. JSON 파싱·언어선택·중복제거·폴백 로직만 검증한다.
실제 번역 품질과 크로스링구얼 검색 개선은 라이브 docker 로 별도 확인(worklog).
"""
from __future__ import annotations

from unittest.mock import patch

from app.services.llm.client import LLMResponse
from app.services.nas_search import query_multilingual
from app.services.nas_search.query_multilingual import expand_query_multilingual

MSG = "설화수 웨이보 마케팅 성과 자료 좀 찾아줘"


def _resp(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        input_tokens=10,
        output_tokens=8,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        model="claude-haiku-4-5-20251001",
        trace_id=None,
        cost_usd=0.0,
    )


_GOOD_JSON = (
    '{"ko": "설화수 웨이보 마케팅 성과", "zh": "雪花秀 微博 营销 业绩", '
    '"en": "Sulwhasoo Weibo marketing performance"}'
)


class TestExpandQueryMultilingual:
    def test_returns_three_variants_on_success(self) -> None:
        with patch.object(query_multilingual, "call_claude", return_value=_resp(_GOOD_JSON)):
            out = expand_query_multilingual(MSG)
        assert out == [
            "설화수 웨이보 마케팅 성과",
            "雪花秀 微博 营销 业绩",
            "Sulwhasoo Weibo marketing performance",
        ]

    def test_parses_json_with_codefence_and_preamble(self) -> None:
        noisy = "검색어입니다:\n```json\n" + _GOOD_JSON + "\n```"
        with patch.object(query_multilingual, "call_claude", return_value=_resp(noisy)):
            out = expand_query_multilingual(MSG)
        assert len(out) == 3 and out[1] == "雪花秀 微博 营销 业绩"

    def test_respects_configured_lang_order_and_subset(self) -> None:
        with patch.object(
            query_multilingual.settings, "nas_multilingual_query_langs", "zh,ko"
        ), patch.object(query_multilingual, "call_claude", return_value=_resp(_GOOD_JSON)):
            out = expand_query_multilingual(MSG)
        assert out == ["雪花秀 微博 营销 业绩", "설화수 웨이보 마케팅 성과"]

    def test_dedupes_identical_variants(self) -> None:
        dup = '{"ko": "마케팅", "zh": "마케팅", "en": "marketing"}'
        with patch.object(query_multilingual, "call_claude", return_value=_resp(dup)):
            out = expand_query_multilingual(MSG)
        assert out == ["마케팅", "marketing"]

    def test_drops_overlong_lang_value(self) -> None:
        junk = "x" * (query_multilingual._MAX_LANG_CHARS + 1)
        payload = f'{{"ko": "설화수", "zh": "{junk}", "en": "Sulwhasoo"}}'
        with patch.object(query_multilingual, "call_claude", return_value=_resp(payload)):
            out = expand_query_multilingual(MSG)
        assert out == ["설화수", "Sulwhasoo"]

    def test_disabled_returns_single_original(self) -> None:
        with patch.object(
            query_multilingual.settings, "nas_multilingual_query_enabled", False
        ), patch.object(query_multilingual, "call_claude") as mock_call:
            out = expand_query_multilingual(MSG)
        assert out == [MSG]
        mock_call.assert_not_called()

    def test_llm_exception_falls_back_to_original(self) -> None:
        with patch.object(
            query_multilingual, "call_claude", side_effect=RuntimeError("api down")
        ):
            assert expand_query_multilingual(MSG) == [MSG]

    def test_unparseable_output_falls_back_to_original(self) -> None:
        with patch.object(query_multilingual, "call_claude", return_value=_resp("죄송합니다")):
            assert expand_query_multilingual(MSG) == [MSG]

    def test_empty_json_object_falls_back_to_original(self) -> None:
        with patch.object(query_multilingual, "call_claude", return_value=_resp("{}")):
            assert expand_query_multilingual(MSG) == [MSG]

    def test_blank_input_returns_empty(self) -> None:
        with patch.object(query_multilingual, "call_claude") as mock_call:
            assert expand_query_multilingual("   ") == []
        mock_call.assert_not_called()
