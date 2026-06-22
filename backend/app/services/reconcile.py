from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tax_invoice import TaxInvoice
from app.models.transaction import Transaction


async def reconcile_invoices(db: AsyncSession, date_tolerance_days: int = 5):
    """Match tax invoices to transactions.

    Matching criteria:
    1. Total amount matches
    2. Date within tolerance
    3. Supplier/counterpart name similarity (if available)
    """
    unmatched_invoices = await db.execute(
        select(TaxInvoice).where(TaxInvoice.match_status == "unmatched")
    )
    invoices = list(unmatched_invoices.scalars().all())

    # 내부이체로 이미 매칭된 거래(match_status='matched'/'manual')는 후보에서 제외.
    # 그렇지 않으면 한 거래가 내부이체와 세금계산서 양쪽에 중복 점유될 수 있다.
    # auto_match_internal_transactions 와 동일하게 'unmatched' 만 후보로 본다.
    unmatched_txns = await db.execute(
        select(Transaction).where(
            Transaction.match_status == "unmatched",
            Transaction.is_deleted.is_(False),
        )
    )
    txns = list(unmatched_txns.scalars().all())

    matched_count = 0
    used_txn_ids = set()

    for inv in invoices:
        expected_type = "withdrawal" if inv.invoice_type == "purchase" else "deposit"

        for txn in txns:
            if txn.id in used_txn_ids:
                continue
            if txn.transaction_type != expected_type:
                continue
            if txn.amount != inv.total_amount:
                continue
            date_diff = abs((txn.transaction_date - inv.issue_date).days)
            if date_diff > date_tolerance_days:
                continue

            inv.matched_transaction_id = txn.id
            inv.match_status = "matched"
            used_txn_ids.add(txn.id)
            matched_count += 1
            break

    await db.commit()
    return matched_count
