"""은행 어댑터 공통 유틸 (BaseBankAdapter).

은행별 어댑터는 이 클래스를 상속하여 ``detect``, ``extract_account_meta``,
``extract_transactions`` 만 구현하면 된다.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Iterable

logger = logging.getLogger(__name__)

_SUMMARY_KEYWORDS = ("합계", "총합", "소계", "총 ")
_ACCOUNT_NUMBER_PATTERN = re.compile(r"(\d{2,6}(?:-\d{2,7}){1,4}|\d{10,18})")
_HOLDER_PATTERNS = (
    re.compile(r"고객명\s*[:：]\s*(.+)"),
    re.compile(r"예금주명?\s*[:：]\s*(.+?)(?:\s+예금종류|$)"),
)


class BaseBankAdapter:
    """은행 어댑터 베이스. ``priority`` 가 낮을수록 먼저 시도된다."""

    bank_key: str = ""
    bank_name: str = ""
    priority: int = 100

    # --- 정규화 헬퍼 -------------------------------------------------------

    @staticmethod
    def normalize_account_number(raw: str | None) -> str:
        """공백 제거, 하이픈은 유지."""
        if raw is None:
            return ""
        return raw.strip().replace(" ", "")

    @staticmethod
    def parse_amount(val: object) -> Decimal:
        """엑셀 셀 → Decimal. 빈/None/0 → ``Decimal(0)``.

        문자열에 천단위 쉼표가 있어도 처리. 음수, 소수점 대응.
        """
        if val is None:
            return Decimal(0)
        if isinstance(val, Decimal):
            return val
        if isinstance(val, (int, float)):
            return Decimal(str(val))
        text = str(val).replace(",", "").replace(" ", "").strip()
        if not text or text in {"-", "."}:
            return Decimal(0)
        try:
            return Decimal(text)
        except (InvalidOperation, ValueError):
            return Decimal(0)

    @staticmethod
    def parse_datetime(val: object) -> tuple[date, time | None]:
        """다양한 포맷 → (date, time|None).

        지원: datetime, date, "YYYY-MM-DD HH:MM:SS", "YYYY.MM.DD HH:MM:SS",
        "YYYY/MM/DD", "YYYY-MM-DD" 등.
        """
        if val is None:
            raise ValueError("date cell is empty")
        if isinstance(val, datetime):
            t = val.time() if (val.hour or val.minute or val.second) else None
            return val.date(), t
        if isinstance(val, date):
            return val, None
        text = str(val).strip()
        if not text:
            raise ValueError("date cell is empty")

        # 구분자 통일
        normalized = text.replace(".", "-").replace("/", "-")
        # 시간 부분 분리
        if " " in normalized:
            d_part, t_part = normalized.split(" ", 1)
            t_part = t_part.strip()
        else:
            d_part, t_part = normalized, ""

        # YYYY-MM-DD 형태로 파싱
        try:
            d = date.fromisoformat(d_part[:10])
        except ValueError as exc:
            raise ValueError(f"invalid date: '{text}'") from exc

        t: time | None = None
        if t_part:
            # HH:MM 또는 HH:MM:SS
            parts = t_part.split(":")
            if len(parts) >= 2:
                try:
                    h = int(parts[0])
                    m = int(parts[1])
                    s = int(parts[2]) if len(parts) >= 3 else 0
                    t = time(h, m, s)
                except (ValueError, IndexError):
                    t = None
        return d, t

    @staticmethod
    def strip_or_none(val: object) -> str | None:
        if val is None:
            return None
        text = str(val).strip()
        return text or None

    @staticmethod
    def compute_hash(
        account_number: str,
        txn_date: date,
        amount: Decimal,
        txn_type: str,
        balance: Decimal | None,
        description: str | None,
    ) -> str:
        """SHA256(account|date|amount|type|balance|description).

        동일 계좌 내 동일 시점 동일 금액 거래의 중복 업로드를 차단한다.
        """
        payload = "|".join(
            [
                account_number,
                txn_date.isoformat(),
                f"{amount:.2f}",
                txn_type,
                f"{balance:.2f}" if balance is not None else "",
                (description or "").strip(),
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def is_summary_row(row: Iterable[object]) -> bool:
        for cell in row:
            if cell is None:
                continue
            text = str(cell).strip()
            if not text:
                continue
            for kw in _SUMMARY_KEYWORDS:
                if text.startswith(kw):
                    return True
        return False

    @staticmethod
    def find_header_row(ws, keywords: Iterable[str], max_scan: int = 20) -> int:
        """헤더 키워드로 헤더 행 위치 자동 탐색 (0-indexed).

        ``keywords`` 중 하나라도 행 텍스트에 포함되면 해당 행을 헤더로 본다.
        실패 시 -1.
        """
        for r_idx, row in enumerate(
            ws.iter_rows(min_row=1, max_row=max_scan, values_only=True)
        ):
            row_text = " ".join(str(c or "") for c in row)
            for kw in keywords:
                if kw in row_text:
                    return r_idx
        return -1

    @staticmethod
    def extract_account_number_from_text(text: str | None) -> str | None:
        if not text:
            return None
        m = _ACCOUNT_NUMBER_PATTERN.search(str(text))
        return m.group(1) if m else None

    @staticmethod
    def extract_holder_from_text(text: str | None) -> str | None:
        if not text:
            return None
        s = str(text)
        for pat in _HOLDER_PATTERNS:
            m = pat.search(s)
            if m:
                holder = m.group(1).strip()
                # 괄호 안 코드 제거
                holder = re.sub(r"\([^)]*\)$", "", holder).strip()
                return holder or None
        return None
