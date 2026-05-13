"""은행 거래내역 엑셀 자동 인식 + 계좌 자동 등록 패키지.

엔트리포인트는 ``orchestrator`` 모듈의 ``preview_import`` / ``confirm_import``.
어댑터는 ``adapters/*`` 에 은행별로 분리되어 있고, ``registry`` 가 자동 탐지를
담당한다. 기존 ``app.services.excel`` 는 그대로 두어 ``routers/uploads.py``의
백워드 호환을 깨지 않는다 (deprecation 대상).
"""
from app.services.bank_import.adapter import (
    AccountMeta,
    BankAdapter,
    FilenameMeta,
    TransactionDraft,
)
from app.services.bank_import.filename_parser import parse_filename
from app.services.bank_import.orchestrator import (
    ImportConfirmInput,
    ImportPreview,
    ImportResult,
    confirm_import,
    preview_import,
)
from app.services.bank_import.registry import detect_adapter, get_all_adapters

__all__ = [
    "AccountMeta",
    "BankAdapter",
    "FilenameMeta",
    "TransactionDraft",
    "parse_filename",
    "ImportConfirmInput",
    "ImportPreview",
    "ImportResult",
    "confirm_import",
    "preview_import",
    "detect_adapter",
    "get_all_adapters",
]
