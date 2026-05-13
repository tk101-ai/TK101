"""은행 어댑터 자동 탐지.

1) 파일명 hint 가 있으면 해당 은행 어댑터의 ``detect`` 를 우선 호출.
2) 실패하면 priority 순서대로 모든 어댑터의 ``detect`` 시도.
"""
from __future__ import annotations

import logging

from app.services.bank_import.adapter import BankAdapter, FilenameMeta
from app.services.bank_import.adapters import (
    HanaAdapter,
    IBKAdapter,
    KBStarAdapter,
    NonghyupAdapter,
    ShinhanAdapter,
    WooriAdapter,
)
from app.services.bank_import.filename_parser import parse_filename

logger = logging.getLogger(__name__)

ADAPTERS: list[BankAdapter] = [
    KBStarAdapter(),
    IBKAdapter(),
    NonghyupAdapter(),
    ShinhanAdapter(),
    WooriAdapter(),
    HanaAdapter(),
]

ADAPTERS_BY_KEY: dict[str, BankAdapter] = {a.bank_key: a for a in ADAPTERS}


def get_all_adapters() -> list[BankAdapter]:
    return ADAPTERS


def detect_adapter(wb, filename: str) -> tuple[BankAdapter | None, FilenameMeta | None]:
    """워크북 + 파일명으로 어댑터 자동 탐지.

    Returns (adapter, filename_meta). adapter 가 None 이면 탐지 실패.
    """
    fname_meta = parse_filename(filename)

    # 1차: 파일명 hint
    if fname_meta:
        candidate = ADAPTERS_BY_KEY.get(fname_meta.bank_key)
        if candidate is not None:
            try:
                if candidate.detect(wb, fname_meta):
                    logger.info(
                        "adapter detected via filename hint: bank=%s file=%s",
                        candidate.bank_key,
                        filename,
                    )
                    return candidate, fname_meta
            except Exception as e:  # pragma: no cover
                logger.warning("adapter.detect raised for %s: %s", candidate.bank_key, e)

    # 2차: priority 순서로 워크북 검사
    for adapter in sorted(ADAPTERS, key=lambda a: a.priority):
        try:
            if adapter.detect(wb, fname_meta):
                logger.info(
                    "adapter detected via workbook scan: bank=%s file=%s",
                    adapter.bank_key,
                    filename,
                )
                return adapter, fname_meta
        except Exception as e:  # pragma: no cover
            logger.warning(
                "adapter.detect raised for %s on %s: %s",
                adapter.bank_key,
                filename,
                e,
            )

    return None, fname_meta
