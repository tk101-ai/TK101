"""query_refiner 단위 테스트 — 회귀 방지.

LLM 호출(call_claude)은 mocking. 정제 로직(스킵·폴백·정상 경로)만 검증한다.
실제 추출 품질은 라이브 docker 에 실 지시문으로 별도 확인.
"""
from __future__ import annotations

from unittest.mock import patch

from app.services.llm.client import LLMResponse
from app.services.nas_search import query_refiner
from app.services.nas_search.query_refiner import refine_search_query

LONG_INSTRUCTION = "이거랑 나스에서 신세계 서버 증설 관련 자료 찾아서 보고서 써줘"


def _resp(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        input_tokens=10,
        output_tokens=5,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        model="claude-haiku-4-5-20251001",
        trace_id=None,
        cost_usd=0.0,
    )


class TestRefineSearchQuery:
    def test_extracts_keywords_on_success(self) -> None:
        with patch.object(
            query_refiner, "call_claude", return_value=_resp("신세계 서버 증설")
        ) as mock_call:
            out = refine_search_query(LONG_INSTRUCTION)
        assert out == "신세계 서버 증설"
        mock_call.assert_called_once()

    def test_strips_surrounding_whitespace(self) -> None:
        with patch.object(
            query_refiner, "call_claude", return_value=_resp("  신세계 서버 증설\n")
        ):
            assert refine_search_query(LONG_INSTRUCTION) == "신세계 서버 증설"

    def test_short_instruction_skips_llm(self) -> None:
        # _REFINE_MIN_CHARS 미만 → 이미 키워드성. LLM 호출 없이 원본 반환.
        with patch.object(query_refiner, "call_claude") as mock_call:
            out = refine_search_query("마케팅 전략")
        assert out == "마케팅 전략"
        mock_call.assert_not_called()

    def test_disabled_returns_original(self) -> None:
        with patch.object(
            query_refiner.settings, "docgen_query_refine_enabled", False
        ), patch.object(query_refiner, "call_claude") as mock_call:
            out = refine_search_query(LONG_INSTRUCTION)
        assert out == LONG_INSTRUCTION
        mock_call.assert_not_called()

    def test_llm_exception_falls_back_to_original(self) -> None:
        with patch.object(
            query_refiner, "call_claude", side_effect=RuntimeError("api down")
        ):
            assert refine_search_query(LONG_INSTRUCTION) == LONG_INSTRUCTION

    def test_empty_output_falls_back_to_original(self) -> None:
        with patch.object(query_refiner, "call_claude", return_value=_resp("   ")):
            assert refine_search_query(LONG_INSTRUCTION) == LONG_INSTRUCTION

    def test_overlong_output_falls_back_to_original(self) -> None:
        # 잡담 혼입 등으로 과도하게 긴 출력은 신뢰하지 않고 원본 폴백.
        junk = "가" * (query_refiner._REFINE_MAX_OUTPUT_CHARS + 1)
        with patch.object(query_refiner, "call_claude", return_value=_resp(junk)):
            assert refine_search_query(LONG_INSTRUCTION) == LONG_INSTRUCTION

    def test_blank_input_returns_empty(self) -> None:
        with patch.object(query_refiner, "call_claude") as mock_call:
            assert refine_search_query("   ") == ""
        mock_call.assert_not_called()
