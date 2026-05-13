from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction

# 매칭 워크북 기본 윈도우. ±N일 내 거래만 후보.
DEFAULT_MATCH_WINDOW_DAYS = 7


async def auto_match_internal_transactions(db: AsyncSession, date_tolerance_days: int = 3):
    """Match internal transfers: A account withdrawal == B account deposit.

    Matching criteria:
    1. Same amount
    2. Transaction date within tolerance
    3. Different accounts
    4. Both currently unmatched
    """
    unmatched = await db.execute(
        select(Transaction).where(
            Transaction.match_status == "unmatched",
            Transaction.is_deleted.is_(False),
        )
    )
    unmatched_list = list(unmatched.scalars().all())

    withdrawals = [t for t in unmatched_list if t.transaction_type == "withdrawal"]
    deposits = [t for t in unmatched_list if t.transaction_type == "deposit"]

    matched_count = 0
    matched_ids = set()

    for w in withdrawals:
        if w.id in matched_ids:
            continue
        for d in deposits:
            if d.id in matched_ids:
                continue
            if d.account_id == w.account_id:
                continue
            if d.amount != w.amount:
                continue
            date_diff = abs((d.transaction_date - w.transaction_date).days)
            if date_diff > date_tolerance_days:
                continue

            # Match found
            w.matched_transaction_id = d.id
            w.match_status = "matched"
            d.matched_transaction_id = w.id
            d.match_status = "matched"
            matched_ids.add(w.id)
            matched_ids.add(d.id)
            matched_count += 1
            break

    # HIGH-8: 커밋 책임은 라우터로. 서비스에서는 flush 까지만.
    await db.flush()
    return matched_count


# ---------------------------------------------------------------------------
# Wave 2: 매칭 워크북 헬퍼
# ---------------------------------------------------------------------------


async def find_match_candidates(
    db: AsyncSession,
    tx: Transaction,
    window_days: int = DEFAULT_MATCH_WINDOW_DAYS,
) -> list[Transaction]:
    """주어진 거래에 대한 수동 매칭 후보 목록.

    조건:
    - 같은 금액 (amount 일치)
    - 입출금 반대 타입
    - 다른 계좌
    - 거래일 ±window_days 일
    - 미매칭(unmatched)
    - is_deleted=False
    - 자기 자신 제외
    """
    opposite_type = "deposit" if tx.transaction_type == "withdrawal" else "withdrawal"
    date_lo = tx.transaction_date - timedelta(days=window_days)
    date_hi = tx.transaction_date + timedelta(days=window_days)

    stmt = (
        select(Transaction)
        .where(Transaction.id != tx.id)
        .where(Transaction.is_deleted.is_(False))
        .where(Transaction.match_status == "unmatched")
        .where(Transaction.transaction_type == opposite_type)
        .where(Transaction.account_id != tx.account_id)
        .where(Transaction.amount == tx.amount)
        .where(Transaction.transaction_date >= date_lo)
        .where(Transaction.transaction_date <= date_hi)
        .order_by(Transaction.transaction_date.asc())
        .limit(50)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def apply_manual_match(
    db: AsyncSession,
    tx_id_a: uuid.UUID | str,
    tx_id_b: uuid.UUID | str,
) -> tuple[Transaction, Transaction]:
    """두 거래를 manual 매칭으로 양방향 연결.

    조건 검증:
    - 두 거래 모두 존재 + 삭제되지 않음
    - 서로 다른 거래
    - 둘 중 어느 쪽이라도 이미 매칭됐다면 ValueError
    """
    if str(tx_id_a) == str(tx_id_b):
        raise ValueError("동일한 거래끼리는 매칭할 수 없습니다")

    result = await db.execute(
        select(Transaction).where(
            Transaction.id.in_([tx_id_a, tx_id_b]),
            Transaction.is_deleted.is_(False),
        )
    )
    rows = list(result.scalars().all())
    if len(rows) != 2:
        raise LookupError("매칭 대상 거래를 찾을 수 없습니다")

    a, b = rows[0], rows[1]
    if a.match_status not in ("unmatched", "manual") or b.match_status not in (
        "unmatched",
        "manual",
    ):
        raise ValueError("이미 다른 거래와 매칭된 거래입니다")

    a.matched_transaction_id = b.id
    a.match_status = "manual"
    b.matched_transaction_id = a.id
    b.match_status = "manual"

    # HIGH-8: 커밋 책임은 라우터로 이전.
    await db.flush()
    await db.refresh(a)
    await db.refresh(b)
    return a, b


async def remove_match(
    db: AsyncSession,
    tx_id: uuid.UUID | str,
) -> Transaction:
    """매칭 해제 — 양방향으로 unmatched 처리."""
    result = await db.execute(select(Transaction).where(Transaction.id == tx_id))
    tx = result.scalar_one_or_none()
    if tx is None:
        raise LookupError("거래를 찾을 수 없습니다")
    if tx.is_deleted:
        raise ValueError("삭제된 거래입니다")

    counterpart_id = tx.matched_transaction_id
    tx.matched_transaction_id = None
    tx.match_status = "unmatched"

    if counterpart_id is not None:
        result = await db.execute(
            select(Transaction).where(Transaction.id == counterpart_id)
        )
        partner = result.scalar_one_or_none()
        if partner is not None:
            partner.matched_transaction_id = None
            partner.match_status = "unmatched"

    # HIGH-8: 커밋 책임은 라우터로 이전.
    await db.flush()
    await db.refresh(tx)
    return tx
