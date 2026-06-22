"""거래 중복 차단용 정규 해시 (단일 진실의 원천).

거래 dedup 은 ``account_id`` 기반 SHA256 해시 하나로 결정된다. 과거에는 이
알고리즘이 ``orchestrator``·``transactions``·``uploads`` 세 곳에 복제되어
한 곳만 바뀌면 dedup 이 조용히 깨질 위험이 있었다. 이제 모든 적재 경로가
이 모듈의 :func:`compute_transaction_hash` 를 import 해서 사용한다.

포맷(절대 변경 금지 — 기존 적재 해시와 호환):
    "{account_id}|{date_iso}|{amount:.2f}|{type}|{balance:.2f or ''}|{desc.strip()}"
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import date
from decimal import Decimal


def compute_transaction_hash(
    account_id: uuid.UUID | str,
    transaction_date: date,
    amount: Decimal,
    transaction_type: str,
    balance: Decimal | None,
    description: str | None,
) -> str:
    """거래 중복 차단용 SHA256 hex.

    동일 계좌(account_id) 내 동일 시점·금액·종류·잔액·적요 거래의 중복 적재를
    차단한다. 포맷을 바꾸면 기존 적재분과 매칭이 깨지므로 변경하지 말 것.
    """
    parts = [
        str(account_id),
        transaction_date.isoformat(),
        f"{Decimal(amount):.2f}",
        transaction_type,
        f"{Decimal(balance):.2f}" if balance is not None else "",
        (description or "").strip(),
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
