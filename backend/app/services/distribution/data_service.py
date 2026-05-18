"""주차별 종합 데이터 + 명품재고대장 적재 서비스 (T9 Phase B-1 + Phase F-A).

흐름:
1. 라우터가 multipart 업로드 파일을 임시 경로에 저장.
2. ``ingest_excel`` 호출 → 두 시트 파서 실행 + DB UPSERT/replace.
3. 임시 파일 삭제.

DB 전략:
- weekly_summary: UNIQUE(company, period_start, period_end) 기반 UPSERT.
  동일 주차 재업로드 시 자동계산 필드 등 갱신됨.
- products: **회사별 wipe + insert** (Phase F-A). 다른 회사 데이터 보존.
  변동 이력 추적은 v0.3 별도 (snapshot 테이블).

회사 결정 우선순위 (ingest_excel):
1. 명시된 company_label 파라미터
2. 종합관리시트에서 추출된 회사명 (첫 번째)
3. DEFAULT_COMPANY ("래더엑스") fallback
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import DistributionProduct, DistributionWeeklySummary
from app.services.distribution.constants import DEFAULT_COMPANY
from app.services.distribution.products_parser import parse_products_sheet
from app.services.distribution.summary_parser import parse_summary_sheet

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    summary_inserted: int = 0
    summary_updated: int = 0
    products_inserted: int = 0
    products_wiped: int = 0
    # company_label_used: 이번 적재가 어떤 회사로 들어갔는지. 라우터 응답에 포함.
    # None 은 양 시트 모두 비어있어 회사 결정 불필요한 경우만.
    company_label_used: str | None = None
    warnings: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


async def _upsert_weekly_summary(
    db: AsyncSession,
    *,
    rows: list,
    source_file: str,
    user_id: str | None,
    override_company_label: str | None = None,
) -> tuple[int, int]:
    """주차별 데이터 UPSERT. (inserted, updated) 반환.

    override_company_label 명시 시 parsed.company_label 대신 사용 — 라우터가 명시한
    회사로 강제 적재 (Phase F-A 다회사 분리).
    """
    inserted = 0
    updated = 0
    for parsed in rows:
        # 명시된 회사가 있으면 그 값으로 강제 (라우터 폼 입력 우선).
        company = override_company_label or parsed.company_label
        q = await db.execute(
            select(DistributionWeeklySummary).where(
                DistributionWeeklySummary.company_label == company,
                DistributionWeeklySummary.period_start == parsed.period_start,
                DistributionWeeklySummary.period_end == parsed.period_end,
            )
        )
        existing = q.scalar_one_or_none()

        values = dict(parsed.values)  # kr_purchase 등
        if existing is None:
            obj = DistributionWeeklySummary(
                company_label=company,
                period_label=parsed.period_label,
                period_start=parsed.period_start,
                period_end=parsed.period_end,
                raw_row=parsed.raw_row,
                source_file=source_file,
                imported_by=user_id,
                **values,
            )
            db.add(obj)
            inserted += 1
        else:
            # 갱신 — 신규 값으로 덮어쓰기 (모든 필드).
            for k, v in values.items():
                setattr(existing, k, v)
            existing.period_label = parsed.period_label
            existing.raw_row = parsed.raw_row
            existing.source_file = source_file
            existing.imported_by = user_id
            updated += 1
    return inserted, updated


async def _replace_products(
    db: AsyncSession,
    *,
    rows: list,
    source_file: str,
    user_id: str | None,
    company_label: str,
) -> tuple[int, int]:
    """주어진 회사의 products 만 wipe + insert. (inserted, wiped) 반환.

    동작 (T9 Phase F-A):
    1. DELETE WHERE company_label = :company_label
    2. INSERT 각 row with company_label 주입

    다른 회사 데이터 보존. 멱등 (재업로드 시에도 동일 결과 — 같은 회사 wipe + 새 데이터).
    """
    # 해당 회사 기존 행만 삭제 — 다른 회사 데이터 보존.
    wiped_q = await db.execute(
        delete(DistributionProduct).where(
            DistributionProduct.company_label == company_label
        )
    )
    wiped = wiped_q.rowcount or 0

    inserted = 0
    for parsed in rows:
        obj = DistributionProduct(
            company_label=company_label,
            brand=parsed.brand,
            product_name_en=parsed.product_name_en,
            product_code=parsed.product_code,
            category=parsed.category,
            purchase_qty=parsed.purchase_qty,
            domestic_stock_qty=parsed.domestic_stock_qty,
            vn_inventory_move_qty=parsed.vn_inventory_move_qty,
            vn_sales_completed_qty=parsed.vn_sales_completed_qty,
            vn_local_stock_qty=parsed.vn_local_stock_qty,
            supply_price=parsed.supply_price,
            vat=parsed.vat,
            purchase_price=parsed.purchase_price,
            approval_number=parsed.approval_number,
            purchase_date=parsed.purchase_date,
            raw_row=parsed.raw_row,
            source_file=source_file,
            imported_by=user_id,
        )
        db.add(obj)
        inserted += 1
    return inserted, wiped


def _resolve_company_label(
    *,
    explicit: str | None,
    summary_rows: list,
) -> str:
    """업로드 파일이 어떤 회사로 적재될지 결정 (Phase F-A).

    우선순위:
    1. explicit (라우터 form 필드 — 검증된 회사 코드)
    2. 종합관리시트 첫 행의 company_label (자동 추출)
    3. DEFAULT_COMPANY 폴백
    """
    if explicit:
        return explicit
    for parsed in summary_rows:
        candidate = getattr(parsed, "company_label", None)
        if candidate:
            return str(candidate).strip()
    return DEFAULT_COMPANY


async def ingest_excel(
    db: AsyncSession,
    *,
    file_path: Path,
    source_file_name: str,
    user_id: str | None = None,
    company_label: str | None = None,
) -> IngestResult:
    """엑셀 파일 1개 → 종합관리시트 + 명품재고대장 동시 적재.

    company_label 동작 (T9 Phase F-A):
    - 명시되면 양쪽 시트 모두 그 회사로 강제 적재.
    - 명시 안 되면:
      * weekly_summary: 종합관리시트 R5 자동 추출 회사명
      * products: 추출 회사명 → 없으면 DEFAULT_COMPANY ("래더엑스") 폴백

    둘 중 한쪽 시트만 있어도 OK (예: BL샘플파일에는 종합관리시트만 있음).
    """
    result = IngestResult()

    # 1) 종합관리시트 파싱 (먼저 — 회사 결정에 사용).
    summary_rows: list = []
    try:
        summary = parse_summary_sheet(file_path)
        summary_rows = summary.rows
        result.warnings.extend(summary.warnings)
    except Exception as exc:  # pragma: no cover
        logger.exception("summary 파싱 실패")
        result.warnings.append(f"summary 파싱 실패: {exc}")

    # 2) 적재할 회사 결정 (명시 > 자동 추출 > DEFAULT).
    resolved_company = _resolve_company_label(
        explicit=company_label, summary_rows=summary_rows
    )
    result.company_label_used = resolved_company

    # 3) 종합관리시트 UPSERT (결정된 회사로 강제).
    if summary_rows:
        try:
            inserted, updated = await _upsert_weekly_summary(
                db,
                rows=summary_rows,
                source_file=source_file_name,
                user_id=user_id,
                override_company_label=resolved_company,
            )
            result.summary_inserted = inserted
            result.summary_updated = updated
        except Exception as exc:  # pragma: no cover
            logger.exception("summary UPSERT 실패")
            result.warnings.append(f"summary UPSERT 실패: {exc}")

    # 4) 명품재고대장 — 회사별 wipe + insert.
    try:
        products = parse_products_sheet(file_path)
        if products.rows:
            inserted, wiped = await _replace_products(
                db,
                rows=products.rows,
                source_file=source_file_name,
                user_id=user_id,
                company_label=resolved_company,
            )
            result.products_inserted = inserted
            result.products_wiped = wiped
        result.warnings.extend(products.warnings)
    except Exception as exc:  # pragma: no cover
        logger.exception("products 파싱 실패")
        result.warnings.append(f"products 파싱 실패: {exc}")

    await db.commit()
    return result


async def list_weekly_summary(
    db: AsyncSession,
    *,
    limit: int = 50,
    from_date: date | None = None,
    to_date: date | None = None,
    company_label: str | None = None,
) -> list[DistributionWeeklySummary]:
    """기간/회사 필터 적용 조회.

    - from_date: period_end >= from_date (해당일 이후 종료된 주차)
    - to_date: period_start <= to_date (해당일 이전 시작된 주차)
    - company_label: 정확 매칭
    """
    stmt = select(DistributionWeeklySummary)
    if from_date is not None:
        stmt = stmt.where(DistributionWeeklySummary.period_end >= from_date)
    if to_date is not None:
        stmt = stmt.where(DistributionWeeklySummary.period_start <= to_date)
    if company_label is not None:
        stmt = stmt.where(DistributionWeeklySummary.company_label == company_label)
    stmt = stmt.order_by(DistributionWeeklySummary.period_start.desc()).limit(limit)
    q = await db.execute(stmt)
    return list(q.scalars())


async def list_products(
    db: AsyncSession,
    *,
    limit: int = 500,
    company_label: str | None = None,
    brand: str | None = None,
    category: str | None = None,
    search: str | None = None,
) -> list[DistributionProduct]:
    """명품재고대장 조회 with 다중 필터 (T9 Phase F-A).

    필터:
    - company_label: 정확 매칭. None 이면 전체 회사.
    - brand: 정확 매칭. UI 의 브랜드 select 와 매핑.
    - category: 정확 매칭 (Bag/Belts/Ring/Scarf 등).
    - search: product_name_en / product_code ILIKE 부분 매칭.

    정렬: 회사 → 브랜드 → 제품코드 순. UI 그룹 표시에 자연스러움.
    """
    stmt = select(DistributionProduct)
    if company_label is not None:
        stmt = stmt.where(DistributionProduct.company_label == company_label)
    if brand is not None:
        stmt = stmt.where(DistributionProduct.brand == brand)
    if category is not None:
        stmt = stmt.where(DistributionProduct.category == category)
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                DistributionProduct.product_name_en.ilike(pattern),
                DistributionProduct.product_code.ilike(pattern),
            )
        )
    stmt = stmt.order_by(
        DistributionProduct.company_label,
        DistributionProduct.brand,
        DistributionProduct.product_code,
    ).limit(limit)
    q = await db.execute(stmt)
    return list(q.scalars())
