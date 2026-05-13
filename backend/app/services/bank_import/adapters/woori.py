"""우리은행 거래내역 어댑터 (원화 + 외화 통합).

원화 헤더 (R4): ``No. | 거래일시 | 적요 | 기재내용 | 지급(원) | 입금(원) |
거래후 잔액(원) | 취급점 | ...``

외화 헤더 (R5): ``No. | 거래일 | 적요 | 기재내용 | 통화 | 찾으신 금액 |
맡기신 금액 | 잔액 | 거래점 | ...``

→ 원화는 E(지급)/F(입금) 순서 반전, 외화는 F(찾으신=출금)/G(맡기신=입금).
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


class WooriAdapter(BaseBankAdapter):
    bank_key = "woori"
    bank_name = "우리은행"
    priority = 10

    def detect(self, wb, filename_hint: FilenameMeta | None) -> bool:
        if filename_hint and filename_hint.bank_key == self.bank_key:
            return True
        for ws in wb.worksheets:
            for row in ws.iter_rows(min_row=1, max_row=8, values_only=True):
                row_text = " ".join(str(c or "") for c in row)
                if "우리은행 거래내역조회" in row_text or "외화거래내역조회" in row_text:
                    return True
                if "지급(원)" in row_text or "찾으신 금액" in row_text:
                    return True
        return False

    def _is_foreign_sheet(self, ws) -> bool:
        for row in ws.iter_rows(min_row=1, max_row=5, values_only=True):
            for cell in row:
                if cell and "외화거래내역" in str(cell):
                    return True
        header_idx = self.find_header_row(ws, ("찾으신 금액", "맡기신 금액"), max_scan=8)
        return header_idx >= 0

    def extract_account_meta(
        self, wb, filename_hint: FilenameMeta | None
    ) -> AccountMeta:
        ws = wb.active
        account_number = ""
        holder: str | None = None
        for row in ws.iter_rows(min_row=1, max_row=4, values_only=True):
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

        foreign = self._is_foreign_sheet(ws)
        currency = "KRW"
        if foreign:
            # 외화 시트 첫 데이터 행에서 통화 추출
            for row in ws.iter_rows(min_row=6, max_row=6, values_only=True):
                if len(row) > 4 and row[4]:
                    currency = str(row[4]).strip().upper()[:3] or "USD"
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
                for row in ws.iter_rows(min_row=1, max_row=4, values_only=True):
                    for cell in row:
                        if cell is None:
                            continue
                        extracted = self.extract_account_number_from_text(str(cell))
                        if extracted:
                            account_number = self.normalize_account_number(extracted)
                            break
                    if account_number:
                        break
            foreign = self._is_foreign_sheet(ws)
            yield from self._parse_sheet(ws, account_number, foreign)

    def _parse_sheet(
        self, ws, account_number: str, foreign: bool
    ) -> Iterator[TransactionDraft]:
        if foreign:
            header_idx = self.find_header_row(
                ws, ("찾으신 금액", "맡기신 금액"), max_scan=8
            )
        else:
            header_idx = self.find_header_row(ws, ("지급(원)", "입금(원)"), max_scan=8)
        if header_idx < 0:
            return
        for row in ws.iter_rows(min_row=header_idx + 2, values_only=True):
            if not row or all(c is None for c in row):
                continue
            if self.is_summary_row(row):
                continue
            try:
                txn_date, txn_time = self.parse_datetime(row[1])
            except (ValueError, IndexError):
                continue
            if foreign:
                # E: 통화, F: 찾으신(출금), G: 맡기신(입금), H: 잔액
                currency = str(row[4] or "USD").strip().upper()[:3] if len(row) > 4 else "USD"
                withdrawal = self.parse_amount(row[5]) if len(row) > 5 else Decimal(0)
                deposit = self.parse_amount(row[6]) if len(row) > 6 else Decimal(0)
                balance = self.parse_amount(row[7]) if len(row) > 7 else Decimal(0)
            else:
                # E: 지급(출금), F: 입금, G: 잔액
                currency = "KRW"
                withdrawal = self.parse_amount(row[4]) if len(row) > 4 else Decimal(0)
                deposit = self.parse_amount(row[5]) if len(row) > 5 else Decimal(0)
                balance = self.parse_amount(row[6]) if len(row) > 6 else Decimal(0)
            if deposit > 0:
                amount, txn_type = deposit, "deposit"
            elif withdrawal > 0:
                amount, txn_type = withdrawal, "withdrawal"
            else:
                continue
            balance_val = balance if balance != 0 else None
            description = self.strip_or_none(row[2]) if len(row) > 2 else None
            counterpart = self.strip_or_none(row[3]) if len(row) > 3 else None
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
