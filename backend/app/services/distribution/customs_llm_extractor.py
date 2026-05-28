"""면장(통관신고) PDF LLM 추출기 (Priority 4).

기존 헤더/정규식 파서(customs_parser.py)는 면장 양식이 추정치와 다르면 0건이 된다.
면장 PDF 는 통관사·품목·시기마다 레이아웃이 다르고 새 양식이 계속 등장하므로
"위치/정규식"이 아니라 "의미"로 인식할 수 있는 LLM 기반 추출이 필요하다.

흐름:
1. PDF 본문 텍스트 (customs_parser._extract_pdf_text) 를 입력으로 받는다.
2. 시스템 프롬프트 + 면장 텍스트 → Claude (Haiku 기본) Messages API.
3. 모델은 strict JSON (declaration list) 으로 응답하도록 강제.
4. JSON 을 CustomsRow 로 매핑하고 reverse_calc_actual_price 로 실가 역산.

설계 메모:
- LLM 호출은 ``app.services.form_filler.llm_client.call_claude`` 어댑터를 그대로
  재사용한다 — Langfuse 트레이스/비용 계산/캐싱 정책이 한 곳에 모인다.
- 나중에 텐센트 통합 API 로 전환할 때는 어댑터(call_claude) 한 곳만 텐센트
  엔드포인트로 교체하면 된다. 호출자(이 모듈)는 시그니처를 보고 변경 없음.
- 키 없음 / 호출 실패 / JSON 깨짐은 예외 전파하지 않고 ``LLMExtractResult``
  의 warnings 에 사유를 담아 호출자가 fallback 으로 진행하도록 한다.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.config import settings
from app.services.distribution.customs_parser import (
    CustomsRow,
    reverse_calc_actual_price,
)
from app.services.form_filler.llm_client import call_claude

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 시스템 프롬프트 — 면장 도메인 지식 + JSON 스키마 강제.
# 모델이 변경되어도(텐센트 통합 등) 동일 프롬프트로 동작하도록 일반 한국어로 작성.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """당신은 한국 수출입 면장(통관신고서, customs declaration) 데이터 추출 전문가입니다.

사용자가 면장 PDF 에서 추출한 raw 텍스트를 줄 것입니다.
양식·통관사·품목에 따라 레이아웃이 모두 다르지만, 다음 7개 항목은 의미 기반으로 인식해 JSON 배열로 반환하세요.

추출 항목 (정확히 이 키 이름 사용):
- declaration_number: 신고번호 / 면장번호 / 통관번호. 보통 "12345-12-345678" 또는 11~15자리 숫자.
- product: 품명 / 상품명 / 제품명. 한국어 또는 영문 모두 가능.
- bl_number: BL 번호 (Bill of Lading). 영문+숫자 조합.
- declared_price: 신고가 / 단가 / 신고금액. 콤마/통화기호 제거한 숫자 문자열로.
- currency: 통화. "KRW" / "USD" / "CNY" / "JPY" 등 ISO 4217 코드로 정규화.
- stock_qty: 재고수량 / 수량. 정수.
- declared_at: 신고일자. "YYYY-MM-DD" 형식으로 정규화.

규칙:
1. 출력은 반드시 단일 JSON 객체이며, 다음 구조를 따른다:
   {"rows": [ { "declaration_number": "...", "product": "...", ... }, ... ]}
2. 항목을 찾을 수 없으면 그 키는 null. 키 자체를 생략하지 마라.
3. 면장 1건이 여러 품목을 담는 경우, 품목별로 별도 행으로 분리한다 (declaration_number 는 동일하게 반복).
4. 면장이 1건도 인식되지 않으면 {"rows": []} 를 반환한다.
5. 합계/소계/요약 행은 제외한다.
6. JSON 외 텍스트(설명, 코드블록 마커, 인사말)는 절대 포함하지 마라. 첫 글자는 '{', 마지막 글자는 '}'.
7. 숫자에 콤마/통화기호("₩", "$") 가 있으면 제거하되 소수점은 유지한다.
8. 한국 날짜 표기("2026.05.27", "2026년 5월 27일") 는 "2026-05-27" 로 정규화한다.

확실하지 않으면 추측하지 말고 null 을 반환한다 (잘못된 값이 들어가는 것보다 누락이 안전하다)."""


@dataclass
class LLMExtractResult:
    """LLM 추출 결과. parser.CustomsParseResult 와 형태 호환."""

    rows: list[CustomsRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # 디버깅용 — 라이브에서 "왜 빈 결과가 나왔는지" 진단할 때 사용.
    raw_response_preview: str | None = None
    model: str | None = None
    cost_usd: float = 0.0
    trace_id: str | None = None


def _coerce_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    s = str(value).strip()
    if not s:
        return None
    # 통화기호/콤마/공백 제거. 음수 표기는 유지.
    cleaned = re.sub(r"[^\d.\-]", "", s)
    if cleaned in ("", "-", ".", "-."):
        return None
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _coerce_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        return int(Decimal(str(value).replace(",", "").strip()))
    except (InvalidOperation, ValueError):
        return None


def _coerce_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _coerce_str(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _strip_json_envelope(text: str) -> str:
    """모델이 코드블록(```json ... ```) 또는 잡담을 섞어 보낸 경우 JSON 본체만 추출."""
    stripped = text.strip()
    if stripped.startswith("```"):
        # ```json\n...\n``` 또는 ```\n...\n``` 모두 처리.
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```\s*$", "", stripped)
        stripped = stripped.strip()

    # 첫 '{' ~ 마지막 '}' 사이만 잘라낸다 (방어적, 모델이 앞뒤 설명을 붙였을 때).
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return stripped
    return stripped[start : end + 1]


def _row_from_llm_obj(obj: dict[str, Any], ratio: float) -> CustomsRow | None:
    """LLM JSON 1건 → CustomsRow. 식별 가능한 값이 없으면 None."""
    declaration_number = _coerce_str(obj.get("declaration_number"))
    product = _coerce_str(obj.get("product"))
    declared_price = _coerce_decimal(obj.get("declared_price"))

    if declaration_number is None and product is None and declared_price is None:
        return None

    return CustomsRow(
        declaration_number=declaration_number,
        product=product,
        bl_number=_coerce_str(obj.get("bl_number")),
        declared_price=declared_price,
        actual_price=reverse_calc_actual_price(declared_price, ratio=ratio),
        currency=_coerce_str(obj.get("currency")),
        stock_qty=_coerce_int(obj.get("stock_qty")),
        declared_at=_coerce_date(obj.get("declared_at")),
        raw_row={k: obj.get(k) for k in obj},
    )


def _parse_llm_json(text: str, ratio: float) -> tuple[list[CustomsRow], str | None]:
    """LLM 응답 텍스트 → (CustomsRow 리스트, 에러 사유 또는 None).

    JSON 파싱 실패/스키마 불일치는 예외가 아니라 에러 사유 문자열로 돌려준다.
    호출자가 warnings 에 담아 fallback 으로 넘어간다.
    """
    body = _strip_json_envelope(text)
    if not body:
        return [], "LLM 응답이 비어있습니다."
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return [], f"LLM JSON 파싱 실패: {exc.msg} (pos={exc.pos})"

    if not isinstance(payload, dict):
        return [], "LLM 응답 최상위가 객체가 아닙니다."
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        return [], "LLM 응답에 'rows' 배열이 없습니다."

    parsed: list[CustomsRow] = []
    for entry in raw_rows:
        if not isinstance(entry, dict):
            continue
        row = _row_from_llm_obj(entry, ratio)
        if row is not None:
            parsed.append(row)
    return parsed, None


def extract_customs_from_text(
    pdf_text: str,
    *,
    source_file_name: str | None = None,
    model: str | None = None,
) -> LLMExtractResult:
    """면장 PDF 본문 텍스트 → LLM 추출 → CustomsRow 리스트.

    실패 시 예외 전파하지 않는다 — warnings 에 사유를 담아 빈 결과를 돌려준다.
    호출자(parse_customs_pdf) 는 빈 결과면 기존 정규식 경로로 fallback 한다.

    Args:
        pdf_text: PDF 에서 추출한 본문 텍스트.
        source_file_name: 로깅/트레이스 메타용 (없어도 동작).
        model: 모델 ID 오버라이드. None 이면 settings.distribution_customs_llm_model.

    Returns:
        LLMExtractResult — rows / warnings / 디버그 정보(원본 응답 프리뷰, 비용, trace_id).
    """
    result = LLMExtractResult()

    if not settings.distribution_customs_llm_enabled:
        result.warnings.append("면장 LLM 추출이 설정에서 비활성화되어 있습니다.")
        return result

    text = (pdf_text or "").strip()
    if not text:
        result.warnings.append("LLM 추출 입력 텍스트가 비어있습니다.")
        return result

    # 입력 상한 — 비용/지연 방어. 면장 1장 ~ 수천자라 통상 안전 마진.
    max_chars = settings.distribution_customs_llm_max_chars
    if len(text) > max_chars:
        logger.warning(
            "면장 LLM 입력 텍스트가 상한(%d)을 넘어 잘랐습니다 — file=%s, len=%d",
            max_chars,
            source_file_name,
            len(text),
        )
        text = text[:max_chars]
        result.warnings.append(
            f"면장 텍스트가 너무 길어 앞 {max_chars}자만 사용했습니다."
        )

    selected_model = model or settings.distribution_customs_llm_model
    ratio = settings.distribution_customs_declare_ratio

    user_prompt = (
        "다음은 면장 PDF 에서 추출한 텍스트입니다. 위 규칙에 따라 JSON 으로 추출하세요.\n\n"
        f"=== 면장 텍스트 시작 ===\n{text}\n=== 면장 텍스트 끝 ==="
    )

    try:
        response = call_claude(
            system_prompt=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            model=selected_model,
            max_tokens=settings.distribution_customs_llm_max_tokens,
            cache_system=True,
            cache_user_first=False,
            trace_name="customs_extract",
            trace_metadata={"source_file": source_file_name or "unknown"},
        )
    except RuntimeError as exc:
        # API 키 미설정 등 환경 미비. 호출자가 fallback 으로 진행.
        logger.warning("면장 LLM 추출 환경 미비: %s", exc)
        result.warnings.append(f"면장 LLM 추출 환경 미비: {exc}")
        return result
    except Exception as exc:  # noqa: BLE001 — SDK 내부 예외 종류가 다양
        logger.exception(
            "면장 LLM 호출 실패 — file=%s, model=%s", source_file_name, selected_model
        )
        result.warnings.append(f"면장 LLM 호출 실패: {exc}")
        return result

    result.model = response.model
    result.cost_usd = response.cost_usd
    result.trace_id = response.trace_id
    # 디버그 미리보기 — 운영에서 "왜 0건?" 추적용. 길어지면 앞부분만.
    preview = (response.text or "").strip()
    result.raw_response_preview = preview[:500] if preview else None

    rows, err = _parse_llm_json(response.text or "", ratio=ratio)
    if err is not None:
        logger.warning(
            "면장 LLM 응답 파싱 실패 — file=%s, reason=%s, preview=%r",
            source_file_name,
            err,
            result.raw_response_preview,
        )
        result.warnings.append(f"면장 LLM 응답 파싱 실패: {err}")
        return result

    result.rows = rows
    if not rows:
        result.warnings.append("면장 LLM 이 0건을 반환했습니다 (PDF 에 면장 데이터가 없을 수 있음).")
    return result
