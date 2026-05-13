"""하나은행 거래내역 어댑터 (외화 중심).

샘플 헤더 (R7): ``거래일시 | 적요 | 의뢰인 | 통화 | 입금 | 출금 |
거래후잔액 | 구분 | 거래점 | 거래특이사항 | ...``

- 헤더 행: R7 (인덱스 6)
- 다중 시트 (분기별)
- 통화: D 컬럼에서 추출 (USD/CNY/HKD 등)
- 첫 컬럼 A = 거래일시
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

_DETECT_KEYWORDS = ("거래후잔액", "의뢰인")


class HanaAdapter(BaseBankAdapter):
    bank_key = "hana"
    bank_name = "하나은행"
    priority = 20  # 다른 은행과 헤더 키워드 충돌 가능성 낮춤

    def detect(self, wb, filename_hint: FilenameMeta | None) -> bool:
        if filename_hint and filename_hint.bank_key == self.bank_key:
            return True
        for ws in wb.worksheets:
            for row in ws.iter_rows(min_row=1, max_row=10, values_only=True):
                row_text = " ".join(str(c or "") for c in row)
                hits = sum(1 for kw in _DETECT_KEYWORDS if kw in row_text)
                if hits >= 2:
                    return True
        return False

    def extract_account_meta(
        self, wb, filename_hint: FilenameMeta | None
    ) -> AccountMeta:
        ws = wb.worksheets[0]
        account_number = ""
        holder: str | None = None
        for row in ws.iter_rows(min_row=1, max_row=6, values_only=True):
            for cell in row:
                if cell is None:
                    continue
                text = str(cell)
                if not account_number:
                    extracted = self.extract_account_number_from_text(text)
                    if extracted:
                        account_number = self.normalize_account_number(extracted)
                if holder is None:
                    holder = self.extract_holder_from_text(text)

        if not account_number and filename_hint:
            account_number = filename_hint.account_number

        # 통화: 첫 거래 행 D 컬럼
        currency = "USD"
        header_idx = self.find_header_row(ws, _DETECT_KEYWORDS, max_scan=10)
        if header_idx < 0:
            header_idx = 6
        for row in ws.iter_rows(
            min_row=header_idx + 2, max_row=header_idx + 5, values_only=True
        ):
            if len(row) > 3 and row[3]:
                cur_candidate = str(row[3]).strip().upper()[:3]
                if cur_candidate.isalpha():
                    currency = cur_candidate
                    break

        return AccountMeta(
            bank_key=self.bank_key,
            bank_name=self.bank_name,
            account_number=account_number,
            account_holder=holder,
            currency=currency,
            account_label=filename_hint.account_label if filename_hint else None,
            period_year=filename_hint.year if filename_hint else None,
            period_quarter=filename_hint.quarter if filename_hint else None,
        )

    def extract_transactions(self, wb) -> Iterator[TransactionDraft]:
        account_number = ""
        for ws in wb.worksheets:
            if not account_number:
                for row in ws.iter_rows(min_row=1, max_row=6, values_only=True):
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
        header_idx = self.find_header_row(ws, _DETECT_KEYWORDS, max_scan=10)
        if header_idx < 0:
            return
        for row in ws.iter_rows(min_row=header_idx + 2, values_only=True):
            if not row or all(c is None for c in row):
                continue
            if self.is_summary_row(row):
                continue
            try:
                txn_date, txn_time = self.parse_datetime(row[0])
            except (ValueError, IndexError):
                continue
            # B: 적요, C: 의뢰인, D: 통화, E: 입금, F: 출금, G: 잔액
            description = self.strip_or_none(row[1]) if len(row) > 1 else None
            counterpart = self.strip_or_none(row[2]) if len(row) > 2 else None
            currency = (
                str(row[3] or "USD").strip().upper()[:3] if len(row) > 3 else "USD"
            )
            deposit = self.parse_amount(row[4]) if len(row) > 4 else Decimal(0)
            withdrawal = self.parse_amount(row[5]) if len(row) > 5 else Decimal(0)
            balance = self.parse_amount(row[6]) if len(row) > 6 else Decimal(0)
            if deposit > 0:
                amount, txn_type = deposit, "deposit"
            elif withdrawal > 0:
                amount, txn_type = withdrawal, "withdrawal"
            else:
                continue
            balance_val = balance if balance != 0 else None
            yield TransactionDraft(
                transaction_date=txn_date,
                transaction_time=txn_time,
                amount=amount,
                transaction_type=txn_type,
                balance=balance_val,
                description=description,
                counterpart_name=counterpart,
                currency=currency,
                raw_hash=self.compute_hash(
                    account_number, txn_date, amount, txn_type, balance_val, description
                ),
            )
