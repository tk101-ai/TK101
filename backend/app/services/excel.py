from datetime import date
from decimal import Decimal

from openpyxl import load_workbook


def parse_bank_excel(file_bytes: bytes) -> list[dict]:
    """Parse bank statement Excel. Returns list of transaction dicts.

    Expected columns (flexible mapping):
    거래일 | 입금 | 출금 | 잔액 | 상대방(거래처) | 적요(내용)
    """
    wb = load_workbook(filename=file_bytes, read_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return []

    # Find header row
    header_row = None
    for i, row in enumerate(rows):
        row_str = " ".join(str(c or "") for c in row).lower()
        if "거래일" in row_str or "날짜" in row_str or "date" in row_str:
            header_row = i
            break

    if header_row is None:
        header_row = 0

    headers = [str(c or "").strip() for c in rows[header_row]]
    data_rows = rows[header_row + 1:]

    # Column mapping
    col_map = {}
    for i, h in enumerate(headers):
        h_lower = h.lower()
        if "거래일" in h_lower or "날짜" in h_lower or "date" in h_lower:
            col_map["date"] = i
        elif "입금" in h_lower or "credit" in h_lower:
            col_map["credit"] = i
        elif "출금" in h_lower or "debit" in h_lower:
            col_map["debit"] = i
        elif "잔액" in h_lower or "balance" in h_lower:
            col_map["balance"] = i
        elif "상대" in h_lower or "거래처" in h_lower:
            col_map["counterpart"] = i
        elif "적요" in h_lower or "내용" in h_lower or "메모" in h_lower:
            col_map["description"] = i
        elif "금액" in h_lower and "credit" not in col_map and "debit" not in col_map:
            col_map["amount"] = i

    transactions = []
    for row in data_rows:
        if not row or all(c is None for c in row):
            continue

        txn_date = row[col_map["date"]] if "date" in col_map else None
        if txn_date is None:
            continue
        if isinstance(txn_date, str):
            txn_date = date.fromisoformat(txn_date.replace(".", "-").replace("/", "-")[:10])

        # Determine amount and type
        if "credit" in col_map and "debit" in col_map:
            credit = row[col_map["credit"]]
            debit = row[col_map["debit"]]
            if credit and float(credit) > 0:
                amount = Decimal(str(credit))
                txn_type = "deposit"
            elif debit and float(debit) > 0:
                amount = Decimal(str(debit))
                txn_type = "withdrawal"
            else:
                continue
        elif "amount" in col_map:
            raw = float(row[col_map["amount"]])
            amount = Decimal(str(abs(raw)))
            txn_type = "deposit" if raw > 0 else "withdrawal"
        else:
            continue

        transactions.append({
            "transaction_date": txn_date,
            "amount": amount,
            "balance": Decimal(str(row[col_map["balance"]])) if "balance" in col_map and row[col_map["balance"]] else None,
            "counterpart_name": str(row[col_map["counterpart"]]).strip() if "counterpart" in col_map and row[col_map["counterpart"]] else None,
            "description": str(row[col_map["description"]]).strip() if "description" in col_map and row[col_map["description"]] else None,
            "transaction_type": txn_type,
        })

    wb.close()
    return transactions
