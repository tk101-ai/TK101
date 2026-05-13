"""신한은행 거래내역 어댑터.

샘플 헤더 행 (R4): ``No | 전체선택 | 거래일시 | 적요 | 입금액 | 출금액 |
내용 | 잔액 | 거래점명 | 입금인코드 | 메모 | ...``

- 헤더 행: R4 (인덱스 3)
- 다중 시트 (분기별)
- 통화: KRW
- 일부 시트는 거래 0건 (R2에 계좌번호만, 데이터 행 없음)
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterator

from app.services.bank_import.adapter import (
    AccountMeta,
    FilenameMeta,
    TransactionDraft,
)
from app.services.bank_import.base_adapter import BaseBankAdapter

_DETECT_KEYWORDS = ("전체선택", "입금인코드")


class ShinhanAdapter(BaseBankAdapter):
    bank_key = "shinhan"
    bank_name = "신한은행"
    priority = 10

    def detect(self, wb, filename_hint: FilenameMeta | None) -> bool:
        if filename_hint and filename_hint.bank_key == self.bank_key:
            return True
        for ws in wb.worksheets:
            for row in ws.iter_rows(min_row=1, max_row=8, values_only=True):
                row_text = " ".join(str(c or "") for c in row)
                if any(kw in row_text for kw in _DETECT_KEYWORDS):
                    return True
        return False

    def extract_account_meta(
        self, wb, filename_hint: FilenameMeta | None
    ) -> AccountMeta:
        account_number = ""
        for ws in wb.worksheets:
            for row in ws.iter_rows(min_row=1, max_row=5, values_only=True):
                for cell in row:
                    if cell is None:
                        continue
                    extracted = self.extract_account_number_from_text(str(cell))
                    if extracted:
                        account_number = self.normalize_account_number(extracted)
                        break
                if account_number:
                    break
            if account_number:
                break
        if not account_number and filename_hint:
            account_number = filename_hint.account_number
        return AccountMeta(
            bank_key=self.bank_key,
            bank_name=self.bank_name,
            account_number=account_number,
            account_holder=None,  # 신한은 헤더에 예금주 명시 X
            currency="KRW",
            account_label=filename_hint.account_label if filename_hint else None,
            period_year=filename_hint.year if filename_hint else None,
            period_quarter=filename_hint.quarter if filename_hint else None,
        )

    def extract_transactions(self, wb) -> Iterator[TransactionDraft]:
        account_number = ""
        for ws in wb.worksheets:
            if not account_number:
                for row in ws.iter_rows(min_row=1, max_row=3, values_only=True):
                    for cell in row:
                        if cell is None:
                            continue
                        extracted = self.extract_account_number_from_text(str(cell))
                        if extracted:
                            account_number = self.normalize_account_number(extracted)
                            break
                    if account_number:
                        break
            yield from self._parse_sheet(ws, account_number)

    def _parse_sheet(self, ws, account_number: str) -> Iterator[TransactionDraft]:
        header_idx = self.find_header_row(ws, ("전체선택", "입금인코드"), max_scan=10)
        if header_idx < 0:
            return  # 빈 시트
        for row in ws.iter_rows(min_row=header_idx + 2, values_only=True):
            if not row or all(c is None for c in row):
                continue
            if self.is_summary_row(row):
                continue
            try:
                txn_date, txn_time = self.parse_datetime(row[2])  # C
            except (ValueError, IndexError):
                continue
            deposit = self.parse_amount(row[4]) if len(row) > 4 else Decimal(0)
            withdrawal = self.parse_amount(row[5]) if len(row) > 5 else Decimal(0)
            if deposit > 0:
                amount, txn_type = deposit, "deposit"
            elif withdrawal > 0:
                amount, txn_type = withdrawal, "withdrawal"
            else:
                continue
            balance = self.parse_amount(row[7]) if len(row) > 7 else Decimal(0)
            balance_val = balance if balance != 0 else None
            description = self.strip_or_none(row[3]) if len(row) > 3 else None
            counterpart = self.strip_or_none(row[6]) if len(row) > 6 else None
            yield TransactionDraft(
                transaction_date=txn_date,
                transaction_time=txn_time,
                amount=amount,
                transaction_type=txn_type,
                balance=balance_val,
                description=description,
                counterpart_name=counterpart,
                currency="KRW",
                raw_hash=self.compute_hash(
                    account_number, txn_date, amount, txn_type, balance_val, description
                ),
            )
