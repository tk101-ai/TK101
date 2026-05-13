"""IBK 기업은행 거래내역 어댑터 (원화 + 외화 통합).

샘플 (원화) R3: ``빈칸 | 거래일시 | 출금 | 입금 | 거래후잔액 | 거래내용 |
상대계좌번호 | 상대은행 | 메모 | 거래구분 | 수표어음금액 | CMS코드 |
상대계좌예금주명 | ...``

샘플 (외화) R3: ``빈칸 | 거래일시 | 통화 | 입금 | 출금 | 거래후잔액 |
적요 | 수출계좌번호 | 해외수입업자``

→ 외화는 컬럼이 1개 밀려있다 (통화 컬럼이 C에 추가됨). 시트 제목/헤더로 분기.
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

_DETECT_KEYWORDS = ("거래내역조회_입출식", "거래내역조회_외환", "상대계좌예금주명")


class IBKAdapter(BaseBankAdapter):
    bank_key = "ibk"
    bank_name = "IBK기업은행"
    priority = 10

    def detect(self, wb, filename_hint: FilenameMeta | None) -> bool:
        if filename_hint and filename_hint.bank_key == self.bank_key:
            return True
        for ws in wb.worksheets:
            for row in ws.iter_rows(min_row=1, max_row=10, values_only=True):
                row_text = " ".join(str(c or "") for c in row)
                if any(kw in row_text for kw in _DETECT_KEYWORDS):
                    return True
        return False

    def _is_foreign_sheet(self, ws) -> bool:
        for row in ws.iter_rows(min_row=1, max_row=3, values_only=True):
            for cell in row:
                if cell and "외환" in str(cell):
                    return True
        # 헤더에 "통화" 가 있는지
        for row in ws.iter_rows(min_row=3, max_row=3, values_only=True):
            for cell in row:
                if cell and str(cell).strip() == "통화":
                    return True
        return False

    def extract_account_meta(
        self, wb, filename_hint: FilenameMeta | None
    ) -> AccountMeta:
        ws = wb.worksheets[0]
        account_number = ""
        holder: str | None = None
        for row in ws.iter_rows(min_row=1, max_row=3, values_only=True):
            for cell in row:
                if cell is None:
                    continue
                text = str(cell)
                if not account_number:
                    extracted = self.extract_account_number_from_text(text)
                    if extracted:
                        account_number = self.normalize_account_number(extracted)
                if not holder:
                    if "(" in text and ")" in text:
                        # "계좌번호:231-132137-04-011 ((주)티케이..." 형태
                        start = text.find("(")
                        holder_candidate = text[start:].strip()
                        if holder_candidate.startswith("("):
                            # 첫 괄호 짝 추출
                            depth = 0
                            for i, ch in enumerate(holder_candidate):
                                if ch == "(":
                                    depth += 1
                                elif ch == ")":
                                    depth -= 1
                                    if depth == 0:
                                        holder = holder_candidate[: i + 1]
                                        break
                    if not holder:
                        holder = self.extract_holder_from_text(text)

        if not account_number and filename_hint:
            account_number = filename_hint.account_number

        # 통화 결정: 외화 시트면 첫 거래의 통화 셀
        currency = "KRW"
        if self._is_foreign_sheet(ws):
            for row in ws.iter_rows(min_row=4, max_row=4, values_only=True):
                if len(row) > 2 and row[2]:
                    currency = str(row[2]).strip().upper()[:3] or "USD"
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
            foreign = self._is_foreign_sheet(ws)
            yield from self._parse_sheet(ws, account_number, foreign)

    def _parse_sheet(
        self, ws, account_number: str, foreign: bool
    ) -> Iterator[TransactionDraft]:
        # 헤더 행 동적 탐색
        header_kw = ("거래일시", "거래후잔액") if not foreign else ("거래일시", "통화")
        header_idx = self.find_header_row(ws, header_kw, max_scan=10)
        if header_idx < 0:
            header_idx = 2  # 기본 R3
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
                # C: 통화, D: 입금, E: 출금, F: 잔액, G: 적요, I: 해외수입업자
                currency = str(row[2] or "USD").strip().upper()[:3]
                deposit = self.parse_amount(row[3]) if len(row) > 3 else Decimal(0)
                withdrawal = self.parse_amount(row[4]) if len(row) > 4 else Decimal(0)
                balance = self.parse_amount(row[5]) if len(row) > 5 else Decimal(0)
                description = self.strip_or_none(row[6]) if len(row) > 6 else None
                counterpart = self.strip_or_none(row[8]) if len(row) > 8 else None
            else:
                # C: 출금, D: 입금, E: 잔액, F: 거래내용, M: 상대계좌예금주명
                currency = "KRW"
                withdrawal = self.parse_amount(row[2]) if len(row) > 2 else Decimal(0)
                deposit = self.parse_amount(row[3]) if len(row) > 3 else Decimal(0)
                balance = self.parse_amount(row[4]) if len(row) > 4 else Decimal(0)
                description = self.strip_or_none(row[5]) if len(row) > 5 else None
                counterpart = self.strip_or_none(row[12]) if len(row) > 12 else None
            if deposit > 0:
                amount, txn_type = deposit, "deposit"
            elif withdrawal > 0:
                amount, txn_type = withdrawal, "withdrawal"
            else:
                # 외화는 0.00 결산 거래도 있을 수 있으나, 양쪽 모두 0이면 스킵
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
