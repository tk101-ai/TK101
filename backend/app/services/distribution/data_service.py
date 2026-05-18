"""주차별 종합 데이터 + 명품재고대장 적재 서비스 (T9 Phase B-1).

흐름:
1. 라우터가 multipart 업로드 파일을 임시 경로에 저장.
2. ``ingest_excel`` 호출 → 두 시트 파서 실행 + DB UPSERT/replace.
3. 임시 파일 삭제.

DB 전략:
- weekly_summary: UNIQUE(company, period_start, period_end) 기반 UPSERT.
  동일 주차 재업로드 시 자동계산 필드 등 갱신됨.
- products: wipe + insert. 매주 풀 갱신 가정.
  변동 이력 추적은 v0.3 별도 (snapshot 테이블).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import DistributionProduct, DistributionWeeklySummary
from app.services.distribution.products_parser import parse_products_sheet
from app.services.distribution.summary_parser import parse_summary_sheet

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    summary_inserted: int = 0
    summary_updated: int = 0
    products_inserted: int = 0
    products_wiped: int = 0
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
) -> tuple[int, int]:
    """주차별 데이터 UPSERT. (inserted, updated) 반환."""
    inserted = 0
    updated = 0
    for parsed in rows:
        q = await db.execute(
            select(DistributionWeeklySummary).where(
                DistributionWeeklySummary.company_label == parsed.company_label,
                DistributionWeeklySummary.period_start == parsed.period_start,
                DistributionWeeklySummary.period_end == parsed.period_end,
            )
        )
        existing = q.scalar_one_or_none()

        values = dict(parsed.values)  # kr_purchase 등
        if existing is None:
            obj = DistributionWeeklySummary(
                company_label=parsed.company_label,
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
) -> tuple[int, int]:
    """products 테이블 wipe + insert. (inserted, wiped) 반환."""
    # 기존 전체 삭제 (변동 추적 안 함 — v0.3에서 snapshot 으로 확장).
    wiped_q = await db.execute(delete(DistributionProduct))
    wiped = wiped_q.rowcount or 0

    inserted = 0
    for parsed in rows:
        obj = DistributionProduct(
            brand=parsed.brand,
            product_name_en=parsed.product_name_en,
            product_code=parsed.product_code,
            category=parsed.category,
            purchase_qty=parsed.purchase_qty,
            domestic_stock_qty=parsed.domestic_stock_qty,
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


async def ingest_excel(
    db: AsyncSession,
    *,
    file_path: Path,
    source_file_name: str,
    user_id: str | None = None,
) -> IngestResult:
    """엑셀 파일 1개 → 종합관리시트 + 명품재고대장 동시 적재.

    둘 중 하나만 있어도 OK (예: BL샘플파일에는 종합관리시트만 있음).
    """
    result = IngestResult()

    # 1) 종합관리시트
    try:
        summary = parse_summary_sheet(file_path)
        if summary.rows:
            inserted, updated = await _upsert_weekly_summary(
                db,
                rows=summary.rows,
                source_file=source_file_name,
                user_id=user_id,
            )
            result.summary_inserted = inserted
            result.summary_updated = updated
        result.warnings.extend(summary.warnings)
    except Exception as exc:  # pragma: no cover
        logger.exception("summary 파싱 실패")
        result.warnings.append(f"summary 파싱 실패: {exc}")

    # 2) 명품재고대장 (있을 때만 — 시트 없으면 warning 만)
    try:
        products = parse_products_sheet(file_path)
        if products.rows:
            inserted, wiped = await _replace_products(
                db,
                rows=products.rows,
                source_file=source_file_name,
                user_id=user_id,
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
    db: AsyncSession, *, limit: int = 50
) -> list[DistributionWeeklySummary]:
    q = await db.execute(
        select(DistributionWeeklySummary)
        .order_by(DistributionWeeklySummary.period_start.desc())
        .limit(limit)
    )
    return list(q.scalars())


async def list_products(
    db: AsyncSession, *, limit: int = 500
) -> list[DistributionProduct]:
    q = await db.execute(
        select(DistributionProduct)
        .order_by(DistributionProduct.brand, DistributionProduct.product_code)
        .limit(limit)
    )
    return list(q.scalars())
