"""KB국민은행 거래내역 어댑터.

샘플 헤더 행 (R7): ``No | 거래일시 | 보낸분/받는분 | 출금액(원) | 입금액(원) |
잔액(원) | 내 통장 표시 | 메모 | 적요 | 처리점 | 구분 | ...``

- 헤더 행: R7 (인덱스 6)
- 단일 시트
- 통화: KRW 고정
- 입출금: D(출금) / E(입금) — 일반적 순서와 반전
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Iterator

from app.services.bank_import.adapter import (
    AccountMeta,
    FilenameMeta,
    TransactionDraft,
)
from app.services.bank_import.base_adapter import BaseBankAdapter

logger = logging.getLogger(__name__)

_HEADER_KEYWORDS = ("보낸분/받는분", "입금액(원)")
_DETECT_KEYWORDS = ("보낸분/받는분",)


class KBStarAdapter(BaseBankAdapter):
    bank_key = "kbstar"
    bank_name = "KB국민은행"
    priority = 10

    def detect(self, wb, filename_hint: FilenameMeta | None) -> bool:
        if filename_hint and filename_hint.bank_key == self.bank_key:
            return True
        for ws in wb.worksheets:
            for row in ws.iter_rows(min_row=1, max_row=15, values_only=True):
                row_text = " ".join(str(c or "") for c in row)
                if any(kw in row_text for kw in _DETECT_KEYWORDS):
                    return True
        return False

    def extract_account_meta(
        self, wb, filename_hint: FilenameMeta | None
    ) -> AccountMeta:
        ws = wb.active
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
                if not holder:
                    holder = self.extract_holder_from_text(text)
        if not account_number and filename_hint:
            account_number = filename_hint.account_number
        return AccountMeta(
            bank_key=self.bank_key,
            bank_name=self.bank_name,
            account_number=account_number,
            account_holder=holder,
            currency="KRW",
            account_label=filename_hint.account_label if filename_hint else None,
            period_year=filename_hint.year if filename_hint else None,
            period_quarter=filename_hint.quarter if filename_hint else None,
        )

    def extract_transactions(self, wb) -> Iterator[TransactionDraft]:
        ws = wb.active
        header_idx = self.find_header_row(ws, _HEADER_KEYWORDS, max_scan=15)
        if header_idx < 0:
            header_idx = 6  # 기본 R7
        account_number = ""
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

        for row in ws.iter_rows(min_row=header_idx + 2, values_only=True):
            if not row or all(c is None for c in row):
                continue
            if self.is_summary_row(row):
                continue
            try:
                txn_date, txn_time = self.parse_datetime(row[1])
            except ValueError:
                continue
            withdrawal = self.parse_amount(row[3])
            deposit = self.parse_amount(row[4])
            if deposit > 0:
                amount, txn_type = deposit, "deposit"
            elif withdrawal > 0:
                amount, txn_type = withdrawal, "withdrawal"
            else:
                continue
            balance = self.parse_amount(row[5]) if len(row) > 5 else Decimal(0)
            balance_val = balance if balance != 0 else None
            counterpart = self.strip_or_none(row[2]) if len(row) > 2 else None
            description = self.strip_or_none(row[8]) if len(row) > 8 else None
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
