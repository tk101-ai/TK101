"""은행 어댑터 Protocol + 공통 dataclass.

은행별 파서를 일관된 인터페이스로 노출한다. 새 은행을 추가할 때는
``BankAdapter`` Protocol 을 만족하는 클래스를 ``adapters/`` 에 추가하고
``registry.ADAPTERS`` 에 등록하기만 하면 된다.

데이터 클래스는 모두 ``frozen=True`` — 어댑터→오케스트레이터→라우터로
넘어가는 동안 변형되지 않도록 강제한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, time
from decimal import Decimal
from typing import Iterator, Protocol


@dataclass(frozen=True)
class FilenameMeta:
    """파일명에서 추출한 메타. 워크북 메타로 fallback 하기 위한 hint."""

    bank_key: str
    raw_bank_name: str
    account_number: str
    account_label: str | None
    year: int
    quarter: int


@dataclass(frozen=True)
class AccountMeta:
    """엑셀 한 파일이 표현하는 계좌 정보.

    ``currency`` 는 ISO 4217 3자리. ``initial_balance`` 는 첫 거래 직전
    잔액으로, Account 생성 시 초기값으로 사용한다.
    """

    bank_key: str
    bank_name: str
    account_number: str
    account_holder: str | None
    currency: str = "KRW"
    account_label: str | None = None
    period_year: int | None = None
    period_quarter: int | None = None
    initial_balance: Decimal | None = None


@dataclass(frozen=True)
class TransactionDraft:
    """파싱 결과 거래 1건. DB 적재 직전 형태."""

    transaction_date: date
    amount: Decimal
    transaction_type: str  # "deposit" | "withdrawal"
    transaction_time: time | None = None
    balance: Decimal | None = None
    description: str | None = None
    counterpart_name: str | None = None
    currency: str = "KRW"
    raw_hash: str = ""


@dataclass(frozen=True)
class ParseStats:
    """어댑터가 보고하는 진단 통계. preview UI 용."""

    transaction_count: int
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class BankAdapter(Protocol):
    """은행 어댑터 인터페이스.

    ``detect`` 는 워크북 구조와 파일명 hint를 보고 매칭 여부 판단.
    ``extract_account_meta`` 는 1회만 호출. ``extract_transactions``
    는 iterator 로 메모리 효율을 유지한다.
    """

    bank_key: str
    bank_name: str
    priority: int

    def detect(self, wb, filename_hint: FilenameMeta | None) -> bool: ...
    def extract_account_meta(
        self, wb, filename_hint: FilenameMeta | None
    ) -> AccountMeta: ...
    def extract_transactions(self, wb) -> Iterator[TransactionDraft]: ...
