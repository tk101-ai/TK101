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
# 시스템 프롬프트 — 한국 관세청 표준 양식(수출/수입 신고필증) 도메인 지식.
# 양식·통관사가 달라도 항목 번호 ① ~ 57 체계는 일정하므로, 번호 매핑을 모델에게
# 명시적으로 알려준다. 모델이 바뀌어도(텐센트 통합 등) 동일 프롬프트로 동작하도록
# 한국어로 작성.
# ---------------------------------------------------------------------------
_SYSTEM_PROMPT = """당신은 한국 관세청 신고필증(수출신고필증·수입신고필증) 데이터 추출 전문가입니다.

사용자가 신고필증 PDF 에서 추출한 raw 텍스트를 줄 것입니다.
한국 관세청 양식은 항목 번호 체계(① ~ 57)가 표준화되어 있으니, 아래 매핑에 따라 의미 기반으로 추출하세요.

【추출 항목】(JSON 키는 정확히 이 이름 그대로 사용)
- declaration_type: 문서 종류. PDF 제목 "수출신고필증" → "export", "수입신고필증" → "import". 그 외는 null.
- declaration_number: ⑤ 신고번호. 형식 "12345-24-008320X" (5자리-2자리-7자리, 끝 알파벳 가능) 또는 11~15자리 숫자.
- item_name: ㉗ 품명. 일반 품목 분류명 (예: "HAND BAG", "BRACELETS").
- product: ㉚ 모델·규격. 가장 구체적인 제품 표현 (예: "GUCCI BAG", "VAN CLEEF & ARPELS BRACELETS"). 없으면 ㉘ 거래품명, 없으면 ㉗ 품명 폴백.
- bl_number: ㊴ 송품장부호 (예: "SYBT20240712A") 또는 별도 BL번호가 있으면 그 값. 둘 다 있으면 송품장부호 우선.
- unit_price: ㉝ 단가. 1 단위(EA 등) 당 가격. (예: "4,917.1" → "4917.1") 콤마/통화기호 제거.
- declared_price: 신고가격(FOB) 외화. 우선순위 = ㊳ 신고가격(FOB)의 USD/외화 값 → 없으면 ㉞ 금액(USD). 콤마/통화기호 제거한 숫자 문자열.
- declared_price_krw: ㊳ 신고가격(FOB) 옆의 한화 값. 예: "₩19,439,187" → "19439187". 한화 표기가 없으면 null.
- currency: declared_price 의 통화. ㊳ 의 외화 값에 붙은 통화. USD/KRW/CNY/JPY 등 ISO 4217 코드. 외화가 없고 KRW 만 있으면 "KRW".
- stock_qty: ㉜ 수량(단위) 의 수치 부분 (예: "2 (EA)" → 2). 정수.
- declared_at: ⑦ 신고일자. "YYYY-MM-DD" 형식.

【다중 품목 처리 — 매우 중요】
신고필증은 갑지(1페이지) + 을지(2 ~ N페이지) 구조로 한 신고에 여러 품목(란번호)을 담는다.
"(란번호/총란수 : 001/003)" 같은 표기가 보이면 각 란마다 별도 행으로 분리한다.
모든 란은 동일한 declaration_number 를 공유한다 (반복해서 채운다).
란이 3개라면 rows 배열에 3개 객체가 들어간다.

【규칙】
1. 출력은 반드시 단일 JSON 객체이며 구조: {"rows": [ {...}, {...} ]}
2. 항목을 찾을 수 없으면 그 키 값은 null (키 자체는 생략하지 말 것).
3. 신고 자체가 인식되지 않으면 {"rows": []}.
4. 합계/소계 행, "여백" 표기, 발행번호, 페이지 번호는 제외.
5. JSON 외 텍스트(설명·코드블록 마커·인사말) 절대 금지. 첫 글자 '{' , 마지막 글자 '}'.
6. 숫자의 콤마·통화기호("₩","$") 제거, 소수점 유지. "14,041.8" → "14041.8".
7. 날짜는 모든 표기를 "YYYY-MM-DD" 로 정규화. "2024.07.12" → "2024-07-12".
8. 확실하지 않으면 추측 금지 → null. 잘못된 값보다 누락이 안전.

【출력 예시 — "수출신고필증" 1 신고 3 품목 케이스】
입력 텍스트에 제목 "수출신고필증(적재전, 갑지)", "⑤ 신고번호 12865-24-008320X", "⑦ 신고일자 2024-07-12",
"(란번호/총란수 : 001/003) ㉗ 품명 BRACELETS ㉚ VAN CLEEF & ARPELS BRACELETS 2(EA) 단가 7,020.9 ㉞ 금액 14,041.8 ㊳ 신고가격(FOB) $14,042 ₩19,439,187",
"(란번호/총란수 : 002/003) ㉗ HAND BAG ㉚ LOUIS VUITTON SHOULDER BAG 1(EA) 단가 2,551 ㊳ $2,551 ₩3,531,968",
"(란번호/총란수 : 003/003) ㉗ HAND BAG ㉚ GUCCI BAG 2(EA) 단가 4,917.1 ㊳ $9,834 ₩13,614,269",
"㊴ 송품장부호 SYBT20240712A" 가 있으면 출력은:
{"rows": [
  {"declaration_type": "export", "declaration_number": "12865-24-008320X", "item_name": "BRACELETS", "product": "VAN CLEEF & ARPELS BRACELETS", "bl_number": "SYBT20240712A", "unit_price": "7020.9", "declared_price": "14042", "declared_price_krw": "19439187", "currency": "USD", "stock_qty": 2, "declared_at": "2024-07-12"},
  {"declaration_type": "export", "declaration_number": "12865-24-008320X", "item_name": "HAND BAG", "product": "LOUIS VUITTON SHOULDER BAG", "bl_number": "SYBT20240712A", "unit_price": "2551", "declared_price": "2551", "declared_price_krw": "3531968", "currency": "USD", "stock_qty": 1, "declared_at": "2024-07-12"},
  {"declaration_type": "export", "declaration_number": "12865-24-008320X", "item_name": "HAND BAG", "product": "GUCCI BAG", "bl_number": "SYBT20240712A", "unit_price": "4917.1", "declared_price": "9834", "declared_price_krw": "13614269", "currency": "USD", "stock_qty": 2, "declared_at": "2024-07-12"}
]}"""


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


def _coerce_declaration_type(value: Any) -> str | None:
    """declaration_type 도메인 가드. CHECK 제약과 정합해야 한다."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if s in ("export", "import"):
        return s
    return None


def _row_from_llm_obj(obj: dict[str, Any], ratio: float) -> CustomsRow | None:
    """LLM JSON 1건 → CustomsRow. 식별 가능한 값이 없으면 None.

    actual_price 계산:
    - declaration_type == 'export' → declared_price 그대로 (역산 미적용).
    - 'import' 또는 None → declared_price / ratio (수입 가정).
    """
    declaration_number = _coerce_str(obj.get("declaration_number"))
    item_name = _coerce_str(obj.get("item_name"))
    product = _coerce_str(obj.get("product"))
    declared_price = _coerce_decimal(obj.get("declared_price"))

    # 식별 근거 강화: declaration_number / product / item_name / declared_price 중 하나라도.
    if (
        declaration_number is None
        and product is None
        and item_name is None
        and declared_price is None
    ):
        return None

    declaration_type = _coerce_declaration_type(obj.get("declaration_type"))

    return CustomsRow(
        declaration_number=declaration_number,
        declaration_type=declaration_type,
        item_name=item_name,
        product=product,
        bl_number=_coerce_str(obj.get("bl_number")),
        unit_price=_coerce_decimal(obj.get("unit_price")),
        declared_price=declared_price,
        declared_price_krw=_coerce_decimal(obj.get("declared_price_krw")),
        actual_price=reverse_calc_actual_price(
            declared_price,
            declaration_type=declaration_type,
            ratio=ratio,
        ),
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
