"""주간 데이터 fingerprint — 변경 감지용 (T9 Phase D).

용도:
- `distribution_weekly_summary` + `distribution_products` 의 현재 상태를 SHA256 해시로 압축.
- 마지막 자동 생성 시점의 fingerprint 와 비교하여 변경 여부 판단.
- 변경됐으면 새 세션 생성 트리거 (호출자가 generation_service 호출).

저장:
- 단순화: 가장 최신 distribution_session 의 metadata 또는 별도 settings 테이블.
- 여기선 메모리 캐시 + DB select 로 매번 계산 (수십 ms 이내).
- v0.3 에서 별도 fingerprint_log 테이블로 확장.

해시 계산 정책:
- weekly_summary: 가장 최신 1행의 모든 numeric 필드 (kr_purchase, vn_*, *_deposit_req, account/cash_deposit)
- products: brand+product_code+purchase_qty+domestic_stock_qty 튜플 정렬 후 join
"""
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import DistributionProduct, DistributionWeeklySummary

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FingerprintResult:
    fingerprint: str          # SHA256 hex, 64자
    weekly_count: int         # 해시에 포함된 weekly_summary 행 수 (보통 1)
    product_count: int        # 해시에 포함된 product 행 수
    latest_period_label: str | None


def _normalize_decimal(v: Decimal | None) -> str:
    """Decimal → 정규화 문자열 (NULL = ''). 해시 일관성."""
    if v is None:
        return ""
    # quantize 로 정밀도 통일 (소수점 2자리)
    return str(v.quantize(Decimal("0.01")))


async def compute_fingerprint(db: AsyncSession) -> FingerprintResult:
    """현재 weekly_summary 최신 1행 + products 전체로 SHA256 계산."""
    weekly_q = await db.execute(
        select(DistributionWeeklySummary)
        .order_by(DistributionWeeklySummary.period_start.desc())
        .limit(1)
    )
    latest = weekly_q.scalar_one_or_none()

    payload: list = []
    weekly_count = 0
    latest_period_label = None
    if latest is not None:
        weekly_count = 1
        latest_period_label = latest.period_label
        payload.append({
            "type": "weekly",
            "company": latest.company_label,
            "period_start": latest.period_start.isoformat(),
            "period_end": latest.period_end.isoformat(),
            "kr_purchase": _normalize_decimal(latest.kr_purchase),
            "vn_inventory_move": _normalize_decimal(latest.vn_inventory_move),
            "vn_sales_completed": _normalize_decimal(latest.vn_sales_completed),
            "kr_dep_req": _normalize_decimal(latest.kr_purchase_deposit_req),
            "vn_inv_dep_req": _normalize_decimal(latest.vn_inventory_deposit_req),
            "vn_sales_dep_req": _normalize_decimal(latest.vn_sales_deposit_req),
            "account_deposit": _normalize_decimal(latest.account_deposit),
            "cash_deposit": _normalize_decimal(latest.cash_deposit),
        })

    products_q = await db.execute(
        select(
            DistributionProduct.brand,
            DistributionProduct.product_code,
            DistributionProduct.purchase_qty,
            DistributionProduct.domestic_stock_qty,
        )
    )
    product_rows = sorted(
        (
            (r.brand, r.product_code or "", r.purchase_qty or 0, r.domestic_stock_qty or 0)
            for r in products_q
        )
    )
    product_count = len(product_rows)
    payload.extend(
        [{"type": "product", "brand": b, "code": c, "p": pq, "s": sq} for b, c, pq, sq in product_rows]
    )

    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(serialized).hexdigest()
    logger.info(
        "fingerprint 계산 완료: %s (weekly=%d, products=%d)",
        digest[:16], weekly_count, product_count,
    )
    return FingerprintResult(
        fingerprint=digest,
        weekly_count=weekly_count,
        product_count=product_count,
        latest_period_label=latest_period_label,
    )


async def has_changed_since(db: AsyncSession, *, previous_fingerprint: str | None) -> tuple[bool, FingerprintResult]:
    """이전 fingerprint 와 비교. (changed, current_result) 반환."""
    current = await compute_fingerprint(db)
    if not previous_fingerprint:
        return True, current
    return current.fingerprint != previous_fingerprint, current
