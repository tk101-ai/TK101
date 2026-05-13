"""계좌 잔액 스냅샷 계산/재계산/조회 서비스.

설계 메모 (Wave 2 백엔드 D):
- compute_balance_at: target_date 시점의 잔액. 해당 일자(또는 그 이전)의
  거래 중 transaction_date 가 가장 늦은 행의 balance 컬럼을 사용한다.
  같은 날 거래가 여러 건이면 created_at desc 로 마지막 행을 채택.
- recompute_snapshots: 기간 내 거래가 1건이라도 있는 날짜에 대해 스냅샷을 upsert.
  거래가 없는 날짜는 skip (전 거래 기준 캐리포워드는 Phase 2 이슈로 미룸).
  ON CONFLICT (account_id, snapshot_date) DO UPDATE SET balance, currency.
- get_snapshots: interval=daily | monthly. monthly 는 각 월의 가장 늦은 날짜 스냅샷만.
- 모든 함수는 async + AsyncSession 사용. 거래 데이터가 매우 클 수 있어 batch INSERT 권장.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.account_balance_snapshot import AccountBalanceSnapshot
from app.models.transaction import Transaction

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SnapshotRow:
    """get_snapshots 응답용 DTO. ORM 객체를 그대로 노출하지 않는다."""

    account_id: uuid.UUID
    snapshot_date: date
    balance: Decimal
    currency: str


# 내부 헬퍼 ------------------------------------------------------------------
async def _get_account_currency(
    db: AsyncSession, account_id: uuid.UUID
) -> str:
    """계좌 통화 조회. 없으면 'KRW' fallback."""
    result = await db.execute(
        select(Account.currency).where(Account.id == account_id)
    )
    currency = result.scalar_one_or_none()
    return currency or "KRW"


async def _list_account_ids(db: AsyncSession) -> list[uuid.UUID]:
    """활성 계좌의 ID 목록. recompute 전체 모드에서 사용."""
    result = await db.execute(
        select(Account.id).where(Account.is_active.is_(True))
    )
    return [row[0] for row in result.all()]


async def _list_transaction_dates(
    db: AsyncSession,
    account_id: uuid.UUID,
    from_date: date | None,
    to_date: date | None,
) -> list[date]:
    """기간 내 거래가 존재하는 날짜 목록 (오름차순)."""
    query = (
        select(Transaction.transaction_date)
        .where(Transaction.account_id == account_id)
        .where(Transaction.is_deleted.is_(False))
        .group_by(Transaction.transaction_date)
        .order_by(Transaction.transaction_date.asc())
    )
    if from_date is not None:
        query = query.where(Transaction.transaction_date >= from_date)
    if to_date is not None:
        query = query.where(Transaction.transaction_date <= to_date)
    result = await db.execute(query)
    return [row[0] for row in result.all()]


# 공개 API --------------------------------------------------------------------
async def compute_balance_at(
    db: AsyncSession, account_id: uuid.UUID, target_date: date
) -> Decimal | None:
    """target_date 시점의 잔액 추정.

    target_date 이하 거래 중 (transaction_date, created_at) 기준 마지막 행의 balance 사용.
    잔액이 NULL 이거나 거래가 없으면 None 반환.
    """
    query = (
        select(Transaction.balance)
        .where(Transaction.account_id == account_id)
        .where(Transaction.transaction_date <= target_date)
        .where(Transaction.is_deleted.is_(False))
        .where(Transaction.balance.isnot(None))
        .order_by(
            Transaction.transaction_date.desc(),
            Transaction.created_at.desc(),
        )
        .limit(1)
    )
    result = await db.execute(query)
    return result.scalar_one_or_none()


async def recompute_snapshots(
    db: AsyncSession,
    account_id: uuid.UUID | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
) -> tuple[int, int]:
    """기간 내 일별 스냅샷 upsert.

    Returns:
        (computed_rows, account_count)
    """
    if account_id is None:
        account_ids = await _list_account_ids(db)
    else:
        account_ids = [account_id]

    total_rows = 0
    for acct_id in account_ids:
        currency = await _get_account_currency(db, acct_id)
        txn_dates = await _list_transaction_dates(db, acct_id, from_date, to_date)
        if not txn_dates:
            continue

        rows_to_upsert: list[dict] = []
        for d in txn_dates:
            balance = await compute_balance_at(db, acct_id, d)
            if balance is None:
                continue
            rows_to_upsert.append(
                {
                    "id": uuid.uuid4(),
                    "account_id": acct_id,
                    "snapshot_date": d,
                    "balance": balance,
                    "currency": currency,
                }
            )

        if not rows_to_upsert:
            continue

        stmt = pg_insert(AccountBalanceSnapshot).values(rows_to_upsert)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_balance_snapshots_account_date",
            set_={
                "balance": stmt.excluded.balance,
                "currency": stmt.excluded.currency,
            },
        )
        await db.execute(stmt)
        total_rows += len(rows_to_upsert)

    await db.commit()
    return total_rows, len(account_ids)


async def get_snapshots(
    db: AsyncSession,
    account_id: uuid.UUID,
    from_date: date,
    to_date: date,
    interval: str = "monthly",
) -> list[SnapshotRow]:
    """기간 내 스냅샷 조회. interval=daily 면 모두, monthly 면 각 월의 마지막 날짜."""
    interval = interval.lower()
    if interval not in {"daily", "monthly"}:
        raise ValueError("interval 은 'daily' 또는 'monthly' 만 허용합니다")

    query = (
        select(AccountBalanceSnapshot)
        .where(AccountBalanceSnapshot.account_id == account_id)
        .where(AccountBalanceSnapshot.snapshot_date >= from_date)
        .where(AccountBalanceSnapshot.snapshot_date <= to_date)
        .order_by(AccountBalanceSnapshot.snapshot_date.asc())
    )

    if interval == "monthly":
        # 월별 마지막 날짜만 선택. SQL 으로 GROUP BY 후 join 도 가능하지만,
        # 데이터량이 크지 않으므로 파이썬에서 후처리.
        result = await db.execute(query)
        rows = result.scalars().all()
        by_month: dict[str, AccountBalanceSnapshot] = {}
        for r in rows:
            key = r.snapshot_date.strftime("%Y-%m")
            existing = by_month.get(key)
            if existing is None or r.snapshot_date > existing.snapshot_date:
                by_month[key] = r
        rows = sorted(by_month.values(), key=lambda x: x.snapshot_date)
    else:
        result = await db.execute(query)
        rows = result.scalars().all()

    return [
        SnapshotRow(
            account_id=r.account_id,
            snapshot_date=r.snapshot_date,
            balance=r.balance,
            currency=r.currency,
        )
        for r in rows
    ]


async def count_snapshots_in_range(
    db: AsyncSession,
    account_id: uuid.UUID | None,
    from_date: date | None,
    to_date: date | None,
) -> int:
    """recompute 비용 견적용 — 영향 받을 행 개수의 상한."""
    query = select(func.count()).select_from(Transaction).where(
        Transaction.is_deleted.is_(False)
    )
    if account_id is not None:
        query = query.where(Transaction.account_id == account_id)
    if from_date is not None:
        query = query.where(Transaction.transaction_date >= from_date)
    if to_date is not None:
        query = query.where(Transaction.transaction_date <= to_date)
    result = await db.execute(query)
    return result.scalar_one() or 0
