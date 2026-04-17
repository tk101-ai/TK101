from datetime import timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction


async def auto_match_internal_transactions(db: AsyncSession, date_tolerance_days: int = 3):
    """Match internal transfers: A account withdrawal == B account deposit.

    Matching criteria:
    1. Same amount
    2. Transaction date within tolerance
    3. Different accounts
    4. Both currently unmatched
    """
    unmatched = await db.execute(
        select(Transaction).where(Transaction.match_status == "unmatched")
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

    await db.commit()
    return matched_count
