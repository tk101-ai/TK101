"""농협(NH) 거래내역 어댑터.

샘플 헤더 행 (R10): ``구분 | 거래일자 | 출금금액(원) | 입금금액(원) |
거래 후 잔액(원) | 거래내용 | 거래기록사항 | 거래점 | 거래시간 | ...``

- 헤더 행: R10 (인덱스 9)
- 단일 시트
- 통화: KRW
- 날짜 / 시각 분리: B(거래일자) + I(거래시간)
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

_DETECT_KEYWORDS = ("입출금거래내역조회", "거래기록사항", "거래 후 잔액(원)")


class NonghyupAdapter(BaseBankAdapter):
    bank_key = "nonghyup"
    bank_name = "농협은행"
    priority = 10

    def detect(self, wb, filename_hint: FilenameMeta | None) -> bool:
        if filename_hint and filename_hint.bank_key == self.bank_key:
            return True
        for ws in wb.worksheets:
            for row in ws.iter_rows(min_row=1, max_row=12, values_only=True):
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
        for row in ws.iter_rows(min_row=1, max_row=9, values_only=True):
            for cell in row:
                if cell is None:
                    continue
                text = str(cell)
                if not account_number:
                    extracted = self.extract_account_number_from_text(text)
                    if extracted and "-" in extracted:
                        account_number = self.normalize_account_number(extracted)
                if holder is None:
                    # 농협은 셀 분리: "예금주명" 행과 별도 셀
                    pass
        # 농협: 예금주명 (행 7, col C) 으로 직접 추출
        if ws.cell(row=7, column=3).value:
            holder = str(ws.cell(row=7, column=3).value).strip() or None
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
        # 동적 헤더
        header_idx = self.find_header_row(
            ws, ("거래기록사항", "거래 후 잔액(원)"), max_scan=15
        )
        if header_idx < 0:
            header_idx = 9
        account_number = ""
        for row in ws.iter_rows(min_row=1, max_row=8, values_only=True):
            for cell in row:
                if cell is None:
                    continue
                extracted = self.extract_account_number_from_text(str(cell))
                if extracted and "-" in extracted:
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
            except (ValueError, IndexError):
                continue
            # I 컬럼에 거래시간 별도 (있으면 덮어쓰기)
            if len(row) > 8 and row[8]:
                try:
                    t_text = str(row[8]).strip()
                    parts = t_text.split(":")
                    if len(parts) >= 2:
                        from datetime import time as _time

                        h = int(parts[0])
                        m = int(parts[1])
                        s = int(parts[2]) if len(parts) >= 3 else 0
                        txn_time = _time(h, m, s)
                except (ValueError, IndexError):
                    pass
            withdrawal = self.parse_amount(row[2]) if len(row) > 2 else Decimal(0)
            deposit = self.parse_amount(row[3]) if len(row) > 3 else Decimal(0)
            if deposit > 0:
                amount, txn_type = deposit, "deposit"
            elif withdrawal > 0:
                amount, txn_type = withdrawal, "withdrawal"
            else:
                continue
            balance = self.parse_amount(row[4]) if len(row) > 4 else Decimal(0)
            balance_val = balance if balance != 0 else None
            description = self.strip_or_none(row[5]) if len(row) > 5 else None
            # 거래기록사항(F) 을 counterpart 후보, 거래내용(F)을 description으로
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
