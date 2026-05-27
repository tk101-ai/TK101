"""면장(통관신고) 엑셀 파서 (Priority 4).

products_parser.py 와 동일 패턴:
- openpyxl, **헤더 텍스트 기반** 컬럼 매핑 (위치 기반 X — 양식 변경에 강함).
- dataclass 반환, 원본 행(raw_row) 보존.

핵심 비즈니스 규칙 (역산):
- 면장의 신고가(declared_price)는 관세 절감 목적으로 실제 가치의 75% 로 신고된다.
- 실가 역산: ``actual_price = round(declared_price / ratio, 2)``.
  ratio 기본값은 config.py 의 ``distribution_customs_declare_ratio`` (= 0.75).
- ratio <= 0 또는 declared_price 누락/0 이면 actual_price 는 None (안전 가드).

수집 컬럼:
- declaration_number (신고번호/면장번호)
- declared_price (신고가/단가/가격)
- stock_qty (재고/재고수량/수량)
- product (품명/상품명)
- bl_number (BL번호)
- currency (통화)
- declared_at (신고일자)

⚠️ 실제 면장 엑셀 샘플이 아직 없다. 아래 ``_HEADER_CANDIDATES`` 의 한국어 헤더
후보는 추정치이며, 샘플 도착 시 이 dict 만 수정하면 된다.
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

import openpyxl

from app.config import settings

logger = logging.getLogger(__name__)


# ===========================================================================
# 컬럼 매핑 — 실제 면장 엑셀 샘플 도착 시 여기만 수정하면 된다.
# TODO: confirm against real 면장 Excel — 헤더 텍스트는 모두 추정치.
# 각 DB 필드별로 가능한 한국어 헤더 후보 리스트. 정규화된 헤더가 후보에 있으면 매핑.
# ===========================================================================
_HEADER_CANDIDATES: dict[str, list[str]] = {
    # 신고번호(declaration number) — 면장 식별자. partial UNIQUE 키.
    "declaration_number": ["신고번호", "면장번호", "수입신고번호", "통관번호"],
    # 신고가(declared price) — 실가의 75% 로 신고된 금액.
    "declared_price": ["단가", "가격", "신고가격", "신고가", "신고금액"],
    # 재고(stock quantity).
    "stock_qty": ["재고", "재고수량", "수량"],
    # 품명(product name).
    "product": ["품명", "상품명", "제품명", "품목"],
    # 연결 BL 번호.
    "bl_number": ["BL번호", "B/L번호", "BL No", "비엘번호"],
    # 통화.
    "currency": ["통화", "화폐", "currency"],
    # 신고일자.
    "declared_at": ["신고일자", "신고일", "통관일자", "수입신고일"],
}

# 헤더 행으로 인정하려면 최소한 이 필드들 중 하나는 발견돼야 한다.
# (신고번호 또는 신고가 — 면장의 핵심 식별/금액 컬럼.)
_REQUIRED_ANY: tuple[str, ...] = ("declaration_number", "declared_price")


@dataclass
class CustomsRow:
    """파싱된 면장 1행. actual_price 는 파서가 역산해 채운다."""

    declaration_number: str | None = None
    product: str | None = None
    bl_number: str | None = None
    declared_price: Decimal | None = None
    # actual_price: declared_price / ratio 역산값 (파서 계산).
    actual_price: Decimal | None = None
    currency: str | None = None
    stock_qty: int | None = None
    declared_at: date | None = None
    raw_row: dict[str, Any] = field(default_factory=dict)


@dataclass
class CustomsParseResult:
    rows: list[CustomsRow]
    warnings: list[str]


def _normalize_header(raw: object) -> str | None:
    if raw is None:
        return None
    # 병합셀/주석 줄바꿈은 첫 줄만 사용 (예: "신고번호\n(Customs No.)" → "신고번호").
    # 주의: 공백 정규화를 먼저 하면 \n 이 사라져 첫줄 추출이 무력화되므로 split 을 먼저.
    first_line = str(raw).split("\n", 1)[0]
    s = re.sub(r"\s+", " ", first_line).strip()
    return s or None


def _to_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def _to_decimal(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        # "1,000,000" 같은 천단위 콤마 제거.
        cleaned = str(value).replace(",", "").strip()
        if cleaned == "":
            return None
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _to_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    for fmt in ("%Y.%m.%d", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def reverse_calc_actual_price(
    declared_price: Decimal | None,
    *,
    ratio: float | None = None,
) -> Decimal | None:
    """신고가 → 실가 역산. ``actual_price = round(declared_price / ratio, 2)``.

    면장 신고가는 실가의 75% 이므로 ratio(=0.75)로 나눠 실가를 복원한다.

    안전 가드:
    - declared_price 가 None 또는 0 이하 → None (역산 불가/무의미).
    - ratio 가 None 이면 config.distribution_customs_declare_ratio 사용.
    - ratio <= 0 → None (0 나눗셈/음수 비율 방지).
    """
    if declared_price is None:
        return None
    if declared_price <= 0:
        return None
    effective_ratio = (
        ratio if ratio is not None else settings.distribution_customs_declare_ratio
    )
    if effective_ratio <= 0:
        logger.warning(
            "면장 역산 비율이 0 이하 (%s) — actual_price 계산 생략", effective_ratio
        )
        return None
    return (declared_price / Decimal(str(effective_ratio))).quantize(Decimal("0.01"))


def _build_col_map(row: tuple[object, ...]) -> dict[str, int]:
    """엑셀 1행에서 {DB 필드: 컬럼 인덱스} 매핑 추출 (헤더 후보 매칭)."""
    col_map: dict[str, int] = {}
    for col_idx, cell in enumerate(row):
        header = _normalize_header(cell)
        if header is None:
            continue
        for field_name, candidates in _HEADER_CANDIDATES.items():
            if field_name in col_map:
                continue
            if header in candidates:
                col_map[field_name] = col_idx
                break
    return col_map


def _find_header_row(
    rows: list[tuple[object, ...]], max_scan: int = 20
) -> tuple[int, dict[str, int]] | None:
    """헤더 행 인덱스 + 컬럼 매핑 반환. 핵심 컬럼 1개 이상 있어야 헤더로 인정."""
    for idx, row in enumerate(rows[:max_scan]):
        col_map = _build_col_map(row)
        if any(key in col_map for key in _REQUIRED_ANY):
            return idx, col_map
    return None


def parse_customs_sheet(
    file_bytes: bytes,
    *,
    sheet_name: str | None = None,
) -> CustomsParseResult:
    """면장 엑셀 bytes → CustomsRow 리스트.

    Args:
        file_bytes: 업로드된 .xlsx/.xlsm 의 raw bytes.
        sheet_name: 특정 시트명. None 이면 첫 번째(활성) 시트 사용.

    Returns:
        CustomsParseResult(rows, warnings). 헤더 못 찾으면 rows=[] + warning.
    """
    wb = openpyxl.load_workbook(
        io.BytesIO(file_bytes), data_only=True, read_only=True
    )
    if sheet_name is not None:
        if sheet_name not in wb.sheetnames:
            return CustomsParseResult(
                rows=[],
                warnings=[f"시트 '{sheet_name}' 없음. 가용: {wb.sheetnames}"],
            )
        ws = wb[sheet_name]
    else:
        ws = wb.active

    rows = list(ws.iter_rows(values_only=True))

    detected = _find_header_row(rows)
    if detected is None:
        return CustomsParseResult(
            rows=[],
            warnings=[
                "면장 헤더 행을 찾지 못했습니다 "
                "(신고번호/신고가 등). 컬럼 매핑(_HEADER_CANDIDATES) 확인 필요."
            ],
        )
    header_idx, col_map = detected

    parsed: list[CustomsRow] = []
    warnings: list[str] = []

    ratio = settings.distribution_customs_declare_ratio

    for row in rows[header_idx + 1 :]:
        if all(c is None or str(c).strip() == "" for c in row):
            continue

        def get(col_key: str) -> object:
            col_idx = col_map.get(col_key)
            if col_idx is None or col_idx >= len(row):
                return None
            return row[col_idx]

        declaration_number = get("declaration_number")
        product = get("product")
        declared_price = _to_decimal(get("declared_price"))

        # 식별 가능한 값이 전혀 없으면 skip (합계/소계/빈 행 등).
        if (
            (declaration_number is None or str(declaration_number).strip() == "")
            and (product is None or str(product).strip() == "")
            and declared_price is None
        ):
            continue

        actual_price = reverse_calc_actual_price(declared_price, ratio=ratio)

        customs = CustomsRow(
            declaration_number=(
                str(declaration_number).strip()
                if declaration_number not in (None, "")
                else None
            ),
            product=(str(product).strip() if product not in (None, "") else None),
            bl_number=(
                str(get("bl_number")).strip()
                if get("bl_number") not in (None, "")
                else None
            ),
            declared_price=declared_price,
            actual_price=actual_price,
            currency=(
                str(get("currency")).strip()
                if get("currency") not in (None, "")
                else None
            ),
            stock_qty=_to_int(get("stock_qty")),
            declared_at=_to_date(get("declared_at")),
            raw_row={
                k: (str(row[v]) if v < len(row) and row[v] is not None else None)
                for k, v in col_map.items()
            },
        )
        parsed.append(customs)

    return CustomsParseResult(rows=parsed, warnings=warnings)
