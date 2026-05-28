"""customs_llm_extractor 단위 테스트 — 회귀 방지.

LLM 호출 자체는 mocking. JSON 정규화/타입 강제/엔벨로프 제거만 검증한다.
실제 추출 품질은 라이브 docker 에 실 PDF 업로드로 별도 확인.
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import pytest


# 모듈 import 는 backend deps (pydantic_settings 등) 가 있어야 동작.
# 이 테스트는 docker / CI 에서 실행되며, 로컬 syntax check 는 py_compile 로 충분.

from app.services.distribution.customs_llm_extractor import (
    LLMExtractResult,
    _coerce_date,
    _coerce_decimal,
    _coerce_int,
    _coerce_str,
    _parse_llm_json,
    _row_from_llm_obj,
    _strip_json_envelope,
    extract_customs_from_text,
)
from app.services.form_filler.llm_client import LLMResponse


# ---------------------------------------------------------------------------
# 순수 헬퍼 함수
# ---------------------------------------------------------------------------


class TestStripJsonEnvelope:
    def test_strips_json_code_fence(self) -> None:
        text = "```json\n{\"rows\": []}\n```"
        assert _strip_json_envelope(text) == '{"rows": []}'

    def test_strips_bare_code_fence(self) -> None:
        text = "```\n{\"rows\": [1]}\n```"
        assert _strip_json_envelope(text) == '{"rows": [1]}'

    def test_strips_leading_prose(self) -> None:
        # 모델이 앞에 잡담을 붙인 경우, 첫 '{' 부터 사용한다.
        text = "결과는 다음과 같습니다:\n{\"rows\": []}"
        assert _strip_json_envelope(text) == '{"rows": []}'

    def test_strips_trailing_prose(self) -> None:
        text = '{"rows": []}\n위 결과를 확인하세요.'
        assert _strip_json_envelope(text) == '{"rows": []}'

    def test_pure_json_passthrough(self) -> None:
        text = '{"rows": [{"a": 1}]}'
        assert _strip_json_envelope(text) == text

    def test_empty_input(self) -> None:
        assert _strip_json_envelope("") == ""


class TestCoerceDecimal:
    def test_strips_currency_and_comma(self) -> None:
        assert _coerce_decimal("₩1,000,000") == Decimal("1000000")
        assert _coerce_decimal("$1,234.56") == Decimal("1234.56")

    def test_negative_preserved(self) -> None:
        assert _coerce_decimal("-1,000") == Decimal("-1000")

    def test_none_and_empty(self) -> None:
        assert _coerce_decimal(None) is None
        assert _coerce_decimal("") is None
        assert _coerce_decimal("   ") is None

    def test_invalid(self) -> None:
        assert _coerce_decimal("abc") is None

    def test_int_float_decimal(self) -> None:
        assert _coerce_decimal(100) == Decimal("100")
        assert _coerce_decimal(12.5) == Decimal("12.5")
        assert _coerce_decimal(Decimal("3.14")) == Decimal("3.14")


class TestCoerceDate:
    def test_iso(self) -> None:
        from datetime import date

        assert _coerce_date("2026-05-27") == date(2026, 5, 27)

    def test_korean_dot(self) -> None:
        from datetime import date

        assert _coerce_date("2026.05.27") == date(2026, 5, 27)

    def test_slash(self) -> None:
        from datetime import date

        assert _coerce_date("2026/05/27") == date(2026, 5, 27)

    def test_invalid_returns_none(self) -> None:
        assert _coerce_date("2026년 5월 27일") is None  # 한글 표기는 LLM 측에서 정규화 강제
        assert _coerce_date("not a date") is None
        assert _coerce_date(None) is None


class TestCoerceInt:
    def test_int_passthrough(self) -> None:
        assert _coerce_int(42) == 42

    def test_string_with_comma(self) -> None:
        assert _coerce_int("1,234") == 1234

    def test_bool_rejected(self) -> None:
        # bool 은 정수로 강제하지 않는다 (True → 1 이 의도치 않은 stock_qty 가 됨).
        assert _coerce_int(True) is None

    def test_none_and_invalid(self) -> None:
        assert _coerce_int(None) is None
        assert _coerce_int("") is None
        assert _coerce_int("abc") is None


class TestCoerceStr:
    def test_strips_whitespace(self) -> None:
        assert _coerce_str("  hello  ") == "hello"

    def test_empty_string_returns_none(self) -> None:
        assert _coerce_str("") is None
        assert _coerce_str("   ") is None

    def test_none(self) -> None:
        assert _coerce_str(None) is None


# ---------------------------------------------------------------------------
# _row_from_llm_obj — LLM JSON 1건 → CustomsRow.
# ---------------------------------------------------------------------------


class TestRowFromLLMObj:
    def test_complete_row(self) -> None:
        from datetime import date

        obj = {
            "declaration_number": "12345-67-890123",
            "product": "전자제품",
            "bl_number": "BLABC123",
            "declared_price": "1,000,000",
            "currency": "KRW",
            "stock_qty": "50",
            "declared_at": "2026-05-27",
        }
        row = _row_from_llm_obj(obj, ratio=0.75)
        assert row is not None
        assert row.declaration_number == "12345-67-890123"
        assert row.product == "전자제품"
        assert row.bl_number == "BLABC123"
        assert row.declared_price == Decimal("1000000")
        # 역산: 1,000,000 / 0.75 = 1,333,333.33
        assert row.actual_price == Decimal("1333333.33")
        assert row.currency == "KRW"
        assert row.stock_qty == 50
        assert row.declared_at == date(2026, 5, 27)

    def test_empty_row_returns_none(self) -> None:
        # 식별 가능한 값 없음 → None (합계/소계 행).
        assert _row_from_llm_obj({}, ratio=0.75) is None
        assert (
            _row_from_llm_obj(
                {"declaration_number": None, "product": None, "declared_price": None},
                ratio=0.75,
            )
            is None
        )

    def test_partial_row(self) -> None:
        # 신고번호만 있어도 한 행으로 인정.
        row = _row_from_llm_obj({"declaration_number": "12345"}, ratio=0.75)
        assert row is not None
        assert row.declaration_number == "12345"
        assert row.declared_price is None
        assert row.actual_price is None


# ---------------------------------------------------------------------------
# _parse_llm_json — 응답 텍스트 → rows + 에러 사유
# ---------------------------------------------------------------------------


class TestParseLLMJson:
    def test_valid_json(self) -> None:
        text = """{"rows": [
            {"declaration_number": "111", "declared_price": "1000"},
            {"declaration_number": "222", "declared_price": "2000"}
        ]}"""
        rows, err = _parse_llm_json(text, ratio=0.75)
        assert err is None
        assert len(rows) == 2

    def test_empty_rows(self) -> None:
        rows, err = _parse_llm_json('{"rows": []}', ratio=0.75)
        assert err is None
        assert rows == []

    def test_malformed_json(self) -> None:
        rows, err = _parse_llm_json("not json", ratio=0.75)
        assert rows == []
        assert err is not None
        assert "파싱 실패" in err

    def test_missing_rows_key(self) -> None:
        rows, err = _parse_llm_json('{"items": []}', ratio=0.75)
        assert rows == []
        assert err is not None

    def test_rows_not_array(self) -> None:
        rows, err = _parse_llm_json('{"rows": "x"}', ratio=0.75)
        assert rows == []
        assert err is not None

    def test_skips_non_dict_entries(self) -> None:
        # 잡티 섞여 있어도 정상 행만 추출.
        text = '{"rows": ["bad", null, {"declaration_number": "111"}]}'
        rows, err = _parse_llm_json(text, ratio=0.75)
        assert err is None
        assert len(rows) == 1
        assert rows[0].declaration_number == "111"

    def test_strips_code_fence(self) -> None:
        text = '```json\n{"rows": [{"declaration_number": "X"}]}\n```'
        rows, err = _parse_llm_json(text, ratio=0.75)
        assert err is None
        assert len(rows) == 1


# ---------------------------------------------------------------------------
# extract_customs_from_text — 전체 흐름 (LLM 호출 mock).
# ---------------------------------------------------------------------------


def _fake_llm_response(text: str) -> LLMResponse:
    return LLMResponse(
        text=text,
        input_tokens=100,
        output_tokens=50,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        model="claude-haiku-4-5-20251001",
        trace_id=None,
        cost_usd=0.0001,
    )


class TestExtractCustomsFromText:
    def test_empty_input(self) -> None:
        result = extract_customs_from_text("")
        assert result.rows == []
        assert any("비어있" in w for w in result.warnings)

    def test_whitespace_only_input(self) -> None:
        result = extract_customs_from_text("   \n  \t  ")
        assert result.rows == []
        assert any("비어있" in w for w in result.warnings)

    def test_disabled_via_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "distribution_customs_llm_enabled", False)
        result = extract_customs_from_text("some text")
        assert result.rows == []
        assert any("비활성화" in w for w in result.warnings)

    def test_success_path(self) -> None:
        fake_text = (
            '{"rows": ['
            '{"declaration_number": "12345", "product": "A", "declared_price": "1000", "currency": "KRW"}'
            "]}"
        )
        with patch(
            "app.services.distribution.customs_llm_extractor.call_claude",
            return_value=_fake_llm_response(fake_text),
        ):
            result = extract_customs_from_text("면장 텍스트")
        assert len(result.rows) == 1
        assert result.rows[0].declaration_number == "12345"
        assert result.rows[0].declared_price == Decimal("1000")
        assert result.cost_usd > 0
        assert result.raw_response_preview is not None

    def test_malformed_response(self) -> None:
        with patch(
            "app.services.distribution.customs_llm_extractor.call_claude",
            return_value=_fake_llm_response("이상한 응답이에요"),
        ):
            result = extract_customs_from_text("면장 텍스트")
        assert result.rows == []
        assert any("파싱 실패" in w for w in result.warnings)

    def test_runtime_error_swallowed(self) -> None:
        # API 키 미설정 등 RuntimeError → 호출자가 fallback 으로 진행할 수 있도록 swallow.
        with patch(
            "app.services.distribution.customs_llm_extractor.call_claude",
            side_effect=RuntimeError("API 키 없음"),
        ):
            result = extract_customs_from_text("면장 텍스트")
        assert result.rows == []
        assert any("환경 미비" in w for w in result.warnings)

    def test_generic_exception_swallowed(self) -> None:
        with patch(
            "app.services.distribution.customs_llm_extractor.call_claude",
            side_effect=ValueError("SDK boom"),
        ):
            result = extract_customs_from_text("면장 텍스트")
        assert result.rows == []
        assert any("호출 실패" in w for w in result.warnings)

    def test_export_declaration_three_line_items(self) -> None:
        """수출신고필증 3 품목 케이스 — 동일 신고번호로 3행 분리."""
        fake_text = """{"rows": [
            {"declaration_number": "12865-24-008320X", "product": "VAN CLEEF & ARPELS BRACELETS", "bl_number": "SYBT20240712A", "declared_price": "14042", "currency": "USD", "stock_qty": 2, "declared_at": "2024-07-12"},
            {"declaration_number": "12865-24-008320X", "product": "LOUIS VUITTON SHOULDER BAG", "bl_number": "SYBT20240712A", "declared_price": "2551", "currency": "USD", "stock_qty": 1, "declared_at": "2024-07-12"},
            {"declaration_number": "12865-24-008320X", "product": "GUCCI BAG", "bl_number": "SYBT20240712A", "declared_price": "9834", "currency": "USD", "stock_qty": 2, "declared_at": "2024-07-12"}
        ]}"""
        with patch(
            "app.services.distribution.customs_llm_extractor.call_claude",
            return_value=_fake_llm_response(fake_text),
        ):
            result = extract_customs_from_text("면장 텍스트")
        assert len(result.rows) == 3
        # 모든 란이 동일 신고번호 + 송품장부호 공유.
        assert all(r.declaration_number == "12865-24-008320X" for r in result.rows)
        assert all(r.bl_number == "SYBT20240712A" for r in result.rows)
        # 품목별로 다른 product / declared_price.
        assert result.rows[0].product == "VAN CLEEF & ARPELS BRACELETS"
        assert result.rows[0].declared_price == Decimal("14042")
        assert result.rows[2].product == "GUCCI BAG"
        assert result.rows[2].declared_price == Decimal("9834")

    def test_long_text_truncated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.config import settings

        monkeypatch.setattr(settings, "distribution_customs_llm_max_chars", 100)
        long_text = "x" * 1000
        with patch(
            "app.services.distribution.customs_llm_extractor.call_claude",
            return_value=_fake_llm_response('{"rows": []}'),
        ) as mock_call:
            result = extract_customs_from_text(long_text)
        # 호출에 들어간 user content 가 truncate 되었는지 확인.
        kwargs = mock_call.call_args.kwargs
        user_content = kwargs["messages"][0]["content"]
        # 시스템 프롬프트가 아니라 user 메시지에 면장 텍스트가 들어감.
        # truncate 표시: 100자만 살아남음.
        assert long_text[:100] in user_content
        assert long_text not in user_content  # 전체 1000자는 들어가지 않음
        assert any("너무 길어" in w for w in result.warnings)
