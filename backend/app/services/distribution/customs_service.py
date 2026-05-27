"""면장(통관신고) 적재·조회 서비스 (Priority 4).

흐름:
1. 라우터가 multipart 업로드 파일 bytes 를 그대로 전달.
2. ``ingest_customs`` → parse_customs_sheet → DB UPSERT (신고번호 기준).
3. 조회: ``list_declarations`` (회사/검색 필터 + 페이지네이션),
   ``summary`` (건수 + 신고가 합 vs 실가 합).

UPSERT 전략 (멱등):
- declaration_number 가 있으면 그 값 기준 UPSERT — 동일 면장 재업로드 시 갱신.
- declaration_number 가 없는 행은 항상 INSERT (식별 불가 → 중복 판단 불가).

data_service.py 와 동일하게 명시적 에러 처리 + dataclass 결과 반환.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import DistributionCustomsDeclaration
from app.services.distribution.customs_parser import (
    CustomsRow,
    parse_customs_sheet,
)

logger = logging.getLogger(__name__)


@dataclass
class CustomsIngestResult:
    inserted: int = 0
    updated: int = 0
    parsed: int = 0
    # preview: 적재 결과 미리보기 (상위 N행). 라우터 응답에 포함.
    preview: list[CustomsRow] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class CustomsSummary:
    count: int = 0
    total_declared: Decimal = Decimal("0")
    total_actual: Decimal = Decimal("0")


async def _upsert_one(
    db: AsyncSession,
    *,
    parsed: CustomsRow,
    company_label: str | None,
    source_file: str,
    user_id: str | None,
) -> str:
    """면장 1행 UPSERT. 'inserted' 또는 'updated' 반환.

    신고번호가 있으면 기존 행 조회 후 갱신, 없으면 신규 INSERT.
    신고번호 없는 행은 식별 불가 → 항상 INSERT.
    """
    existing = None
    if parsed.declaration_number:
        q = await db.execute(
            select(DistributionCustomsDeclaration).where(
                DistributionCustomsDeclaration.declaration_number
                == parsed.declaration_number
            )
        )
        existing = q.scalar_one_or_none()

    if existing is None:
        obj = DistributionCustomsDeclaration(
            company_label=company_label,
            bl_number=parsed.bl_number,
            declaration_number=parsed.declaration_number,
            product=parsed.product,
            declared_price=parsed.declared_price,
            actual_price=parsed.actual_price,
            currency=parsed.currency,
            stock_qty=parsed.stock_qty,
            declared_at=parsed.declared_at,
            raw_row=parsed.raw_row,
            source_file=source_file,
            imported_by=user_id,
        )
        db.add(obj)
        return "inserted"

    # 갱신 — 새 값으로 덮어쓰기 (역산값 포함).
    existing.company_label = company_label
    existing.bl_number = parsed.bl_number
    existing.product = parsed.product
    existing.declared_price = parsed.declared_price
    existing.actual_price = parsed.actual_price
    existing.currency = parsed.currency
    existing.stock_qty = parsed.stock_qty
    existing.declared_at = parsed.declared_at
    existing.raw_row = parsed.raw_row
    existing.source_file = source_file
    existing.imported_by = user_id
    return "updated"


async def ingest_customs(
    db: AsyncSession,
    *,
    file_bytes: bytes,
    source_file_name: str,
    user_id: str | None = None,
    company_label: str | None = None,
    preview_limit: int = 10,
) -> CustomsIngestResult:
    """면장 엑셀 bytes → 파싱 + 신고번호 기준 UPSERT.

    멱등: 동일 신고번호 재업로드 시 기존 행 갱신 (중복 INSERT 없음).
    """
    result = CustomsIngestResult()

    parse_result = parse_customs_sheet(file_bytes)
    result.warnings.extend(parse_result.warnings)
    result.parsed = len(parse_result.rows)
    result.preview = parse_result.rows[:preview_limit]

    for parsed in parse_result.rows:
        action = await _upsert_one(
            db,
            parsed=parsed,
            company_label=company_label,
            source_file=source_file_name,
            user_id=user_id,
        )
        if action == "inserted":
            result.inserted += 1
        else:
            result.updated += 1

    await db.commit()
    return result


async def list_declarations(
    db: AsyncSession,
    *,
    limit: int = 100,
    offset: int = 0,
    company_label: str | None = None,
    search: str | None = None,
) -> tuple[list[DistributionCustomsDeclaration], int]:
    """면장 조회. (rows, total_count) 반환.

    필터:
    - company_label: 정확 매칭. None 이면 전체 회사.
    - search: 신고번호 / 품명 / BL번호 ILIKE 부분 매칭.

    정렬: 신고일자 desc (NULL 후순위), 적재일 desc.
    """
    base_filters = []
    if company_label is not None:
        base_filters.append(
            DistributionCustomsDeclaration.company_label == company_label
        )
    if search:
        pattern = f"%{search}%"
        base_filters.append(
            or_(
                DistributionCustomsDeclaration.declaration_number.ilike(pattern),
                DistributionCustomsDeclaration.product.ilike(pattern),
                DistributionCustomsDeclaration.bl_number.ilike(pattern),
            )
        )

    count_stmt = select(func.count()).select_from(DistributionCustomsDeclaration)
    for f in base_filters:
        count_stmt = count_stmt.where(f)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = select(DistributionCustomsDeclaration)
    for f in base_filters:
        stmt = stmt.where(f)
    stmt = (
        stmt.order_by(
            DistributionCustomsDeclaration.declared_at.desc().nullslast(),
            DistributionCustomsDeclaration.imported_at.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    rows = list((await db.execute(stmt)).scalars())
    return rows, total


async def summary(
    db: AsyncSession,
    *,
    company_label: str | None = None,
) -> CustomsSummary:
    """면장 집계: 건수 + 신고가 합 vs 실가(역산) 합.

    역산 효과를 한눈에 — total_actual 은 total_declared / 0.75 근사.
    """
    stmt = select(
        func.count(),
        func.coalesce(func.sum(DistributionCustomsDeclaration.declared_price), 0),
        func.coalesce(func.sum(DistributionCustomsDeclaration.actual_price), 0),
    )
    if company_label is not None:
        stmt = stmt.where(
            DistributionCustomsDeclaration.company_label == company_label
        )
    row = (await db.execute(stmt)).one()
    return CustomsSummary(
        count=int(row[0]),
        total_declared=Decimal(str(row[1])),
        total_actual=Decimal(str(row[2])),
    )
