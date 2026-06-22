"""파일 업로드 → preview / confirm 흐름을 조율한다.

- ``preview_import``: 파일 1개 → 메타 인식 → 기존 계좌 매칭 후보 → 거래 건수 추정 (DB write X)
- ``confirm_import``: 파일 + (account_id | create_account) → 거래 일괄 적재 + 중복 차단

대용량 워크북 가능성을 고려해 openpyxl 은 ``read_only=True, data_only=True`` 로
열고, transaction draft 는 generator 로 yield 한다. INSERT 는 chunk 단위로
``INSERT ... ON CONFLICT DO NOTHING`` 을 사용해 중복 행만 스킵.
"""
from __future__ import annotations

import io
import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from openpyxl import load_workbook
from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.transaction import Transaction
from app.models.upload_log import UploadLog
from app.schemas.account import AccountCreate
from app.services.bank_import.adapter import (
    AccountMeta,
    BankAdapter,
    TransactionDraft,
)
from app.services.bank_import.hashing import compute_transaction_hash
from app.services.bank_import.registry import detect_adapter

logger = logging.getLogger(__name__)

# CRITICAL-2: 적재 직전 account_id 기반 정규 해시(hashing.compute_transaction_hash)로
# 재계산한다. 어댑터가 채운 account_number 기반 d.raw_hash 는 사용하지 않는다.

INSERT_CHUNK_SIZE = 200


@dataclass
class SimilarAccount:
    id: str
    bank_name: str
    account_number: str
    account_holder: str | None
    currency: str
    account_label: str | None
    score: float  # 0.0 ~ 1.0


@dataclass
class ImportPreview:
    file_name: str
    adapter_detected: str | None  # bank_key
    bank_name: str | None
    account_meta: AccountMeta | None
    existing_account_id: str | None
    similar_accounts: list[SimilarAccount] = field(default_factory=list)
    transaction_count: int = 0
    duplicate_count_estimate: int = 0
    parse_warnings: list[str] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


@dataclass
class ImportConfirmInput:
    file_bytes: bytes
    file_name: str
    user_id: uuid.UUID
    account_id: str | None = None  # 기존 계좌 사용
    create_account: AccountCreate | None = None  # 새 계좌 등록
    on_duplicate: str = "skip"  # "skip" only for now


@dataclass
class ImportResult:
    upload_log_id: str
    account_id: str
    bank_key: str | None
    imported_count: int
    duplicate_count: int
    error_count: int
    status: str  # completed | partial | failed
    errors: list[dict[str, Any]] = field(default_factory=list)


# -------------------------------------------------------------------------
# 헬퍼
# -------------------------------------------------------------------------


def _safe_filename(filename: str | None) -> str:
    if not filename:
        return "unknown.xlsx"
    return os.path.basename(filename)


def _open_workbook(file_bytes: bytes):
    buf = io.BytesIO(file_bytes)
    return load_workbook(filename=buf, read_only=True, data_only=True)


def _digits_only(s: str | None) -> str:
    if not s:
        return ""
    return "".join(c for c in s if c.isdigit())


async def _find_existing_account(
    db: AsyncSession, account_number: str, bank_key: str | None
) -> tuple[Account | None, list[SimilarAccount]]:
    """계좌번호 정확 일치 우선, 그 외 digits-only fuzzy 매칭 후보 반환."""
    if not account_number:
        return None, []

    digits = _digits_only(account_number)
    # 1) 정확 일치
    exact_stmt = select(Account).where(Account.account_number == account_number)
    res = await db.execute(exact_stmt)
    exact = res.scalar_one_or_none()
    if exact is not None:
        return exact, []

    # 2) 비슷한 계좌 (digits-only 비교) — bank_key 와 동일 은행 우선
    # PostgreSQL: REGEXP_REPLACE(account_number, '[^0-9]', '', 'g')
    digits_expr = func.regexp_replace(Account.account_number, r"[^0-9]", "", "g")
    similar_stmt = (
        select(Account)
        .where(or_(digits_expr == digits, digits_expr.like(f"%{digits[-6:]}%")))
        .limit(5)
    )
    res = await db.execute(similar_stmt)
    candidates = list(res.scalars().all())
    similar: list[SimilarAccount] = []
    for cand in candidates:
        cand_digits = _digits_only(cand.account_number)
        if cand_digits == digits:
            score = 1.0
        elif digits and cand_digits.endswith(digits[-6:]):
            score = 0.6
        else:
            score = 0.3
        similar.append(
            SimilarAccount(
                id=str(cand.id),
                bank_name=cand.bank_name,
                account_number=cand.account_number,
                account_holder=cand.account_holder,
                currency=cand.currency or "KRW",
                account_label=cand.account_label,
                score=score,
            )
        )
    return None, similar


def _drafts_for_preview(
    adapter: BankAdapter, wb, max_count: int = 20000
) -> tuple[list[TransactionDraft], list[str]]:
    """preview 단계: 모두 메모리에 모은다 (분기당 ~수천 건 수준). 한도 초과 시 warning."""
    drafts: list[TransactionDraft] = []
    warnings: list[str] = []
    try:
        for i, d in enumerate(adapter.extract_transactions(wb)):
            if i >= max_count:
                warnings.append(
                    f"거래 건수가 {max_count} 건을 초과해 미리보기에서 잘랐습니다"
                )
                break
            drafts.append(d)
    except Exception as e:  # 어댑터 내부 예외는 message로 보고
        warnings.append(f"파싱 도중 오류: {e}")
    return drafts, warnings


async def _count_existing_hashes(
    db: AsyncSession, account_id: str, hashes: list[str]
) -> int:
    if not hashes:
        return 0
    stmt = select(func.count(Transaction.id)).where(
        Transaction.account_id == account_id,
        Transaction.transaction_hash.in_(hashes),
    )
    res = await db.execute(stmt)
    return int(res.scalar() or 0)


# -------------------------------------------------------------------------
# preview
# -------------------------------------------------------------------------


async def preview_import(
    db: AsyncSession, file_bytes: bytes, file_name: str
) -> ImportPreview:
    """파일을 열어 메타·거래 건수·중복 추정만 보고. DB 적재 없음."""
    safe_name = _safe_filename(file_name)
    preview = ImportPreview(
        file_name=safe_name,
        adapter_detected=None,
        bank_name=None,
        account_meta=None,
        existing_account_id=None,
    )

    try:
        wb = _open_workbook(file_bytes)
    except Exception as e:
        preview.parse_errors.append(f"엑셀 파일 열기 실패: {e}")
        return preview

    try:
        adapter, _fname_meta = detect_adapter(wb, safe_name)
        if adapter is None:
            preview.parse_errors.append(
                "은행 형식을 자동 감지할 수 없습니다. 파일명 또는 양식을 확인하세요."
            )
            return preview

        preview.adapter_detected = adapter.bank_key
        preview.bank_name = adapter.bank_name

        try:
            meta = adapter.extract_account_meta(wb, _fname_meta)
            preview.account_meta = meta
        except Exception as e:
            preview.parse_errors.append(f"계좌 메타 추출 실패: {e}")
            return preview

        drafts, warnings = _drafts_for_preview(adapter, wb)
        preview.transaction_count = len(drafts)
        preview.parse_warnings.extend(warnings)

        # 기존 계좌 찾기
        existing, similar = await _find_existing_account(
            db, meta.account_number, adapter.bank_key
        )
        if existing is not None:
            preview.existing_account_id = str(existing.id)
            # 기존 계좌면 중복 거래 추정
            hashes = [d.raw_hash for d in drafts if d.raw_hash]
            preview.duplicate_count_estimate = await _count_existing_hashes(
                db, str(existing.id), hashes
            )
        preview.similar_accounts = similar
    finally:
        wb.close()

    return preview


# -------------------------------------------------------------------------
# confirm
# -------------------------------------------------------------------------


async def _ensure_account(
    db: AsyncSession,
    meta: AccountMeta,
    inp: ImportConfirmInput,
    adapter: BankAdapter,
) -> Account:
    """account_id가 있으면 조회, create_account이 있으면 생성. 둘 다 있으면 account_id 우선."""
    if inp.account_id:
        res = await db.execute(select(Account).where(Account.id == inp.account_id))
        acc = res.scalar_one_or_none()
        if acc is None:
            raise HTTPException(status_code=404, detail="account_id 가 유효하지 않습니다")
        return acc

    # 새 계좌 등록
    create = inp.create_account
    if create is None:
        # 메타에서 자동 생성 (호출자가 명시적으로 동의했다고 간주 X)
        raise HTTPException(
            status_code=422,
            detail="account_id 또는 create_account 중 하나는 필수입니다",
        )

    # 중복 number 차단 (별도 동시성 안전을 위해 DB UNIQUE 도 신뢰)
    res = await db.execute(
        select(Account).where(Account.account_number == create.account_number)
    )
    existing = res.scalar_one_or_none()
    if existing is not None:
        return existing

    new_acc = Account(
        bank_name=create.bank_name or adapter.bank_name,
        account_number=create.account_number,
        account_holder=create.account_holder,
        business_registration_no=create.business_registration_no,
        account_type=create.account_type or ("foreign" if meta.currency != "KRW" else "general"),
        currency=create.currency or meta.currency,
        alias=create.alias,
        account_label=create.account_label or meta.account_label,
    )
    db.add(new_acc)
    await db.flush()
    return new_acc


async def _bulk_insert_transactions(
    db: AsyncSession,
    account_id: str,
    upload_log_id: str,
    drafts: list[TransactionDraft],
) -> tuple[int, int, list[dict[str, Any]]]:
    """ON CONFLICT DO NOTHING 으로 chunk insert. (imported, duplicates, errors) 반환.

    transaction_hash 가 unique constraint 의 키이므로 중복 행은 자동 스킵.
    """
    if not drafts:
        return 0, 0, []

    imported = 0
    duplicates = 0
    errors: list[dict[str, Any]] = []

    table = Transaction.__table__
    for chunk_start in range(0, len(drafts), INSERT_CHUNK_SIZE):
        chunk = drafts[chunk_start : chunk_start + INSERT_CHUNK_SIZE]
        rows = []
        for d in chunk:
            # CRITICAL-2 fix: account_id 기반 통일 해시로 재계산.
            # 어댑터가 채운 account_number 기반 d.raw_hash 는 사용하지 않는다.
            tx_hash = compute_transaction_hash(
                account_id,
                d.transaction_date,
                d.amount,
                d.transaction_type,
                d.balance,
                d.description,
            )
            rows.append(
                {
                    "account_id": account_id,
                    "upload_log_id": upload_log_id,
                    "transaction_date": d.transaction_date,
                    "amount": d.amount,
                    "balance": d.balance,
                    "counterpart_name": d.counterpart_name,
                    "description": d.description,
                    "transaction_type": d.transaction_type,
                    "transaction_hash": tx_hash,
                    "match_status": "unmatched",
                    "is_deleted": False,
                }
            )
        try:
            stmt = insert(table).values(rows)
            # CRITICAL-3+4 fix: partial unique index (transaction_hash IS NOT NULL
            # AND is_deleted = false) 와 일치하도록 index_where 명시.
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["account_id", "transaction_hash"],
                index_where=(
                    "transaction_hash IS NOT NULL AND is_deleted = false"
                ),
            )
            # CTE returning 으로 실제 insert 카운트 받기
            stmt = stmt.returning(table.c.id)
            res = await db.execute(stmt)
            inserted_ids = list(res.scalars().all())
            imported += len(inserted_ids)
            duplicates += len(chunk) - len(inserted_ids)
        except Exception as e:
            errors.append({"chunk_start": chunk_start, "error": str(e)})
            logger.exception("bulk insert failed at chunk %d", chunk_start)

    return imported, duplicates, errors


async def confirm_import(
    db: AsyncSession, inp: ImportConfirmInput
) -> ImportResult:
    """파일 + (account_id | create_account) → 적재 + UploadLog 갱신."""
    safe_name = _safe_filename(inp.file_name)
    try:
        wb = _open_workbook(inp.file_bytes)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"엑셀 파일 열기 실패: {e}")

    try:
        adapter, fname_meta = detect_adapter(wb, safe_name)
        if adapter is None:
            raise HTTPException(
                status_code=422,
                detail="은행 형식을 자동 감지할 수 없습니다",
            )

        try:
            meta = adapter.extract_account_meta(wb, fname_meta)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"계좌 메타 추출 실패: {e}")

        # 계좌 확보
        account = await _ensure_account(db, meta, inp, adapter)

        # 업로드 로그 생성
        period_label: str | None = None
        if meta.period_year and meta.period_quarter:
            period_label = f"{meta.period_year}-{meta.period_quarter}사분기"
        log = UploadLog(
            user_id=inp.user_id,
            filename=safe_name,
            upload_type="transaction",
            account_id=account.id,
            status="processing",
            bank_key=adapter.bank_key,
            period_label=period_label,
        )
        db.add(log)
        await db.flush()

        # 거래 파싱 및 적재
        drafts, warnings = _drafts_for_preview(adapter, wb)
        if not drafts:
            log.status = "completed"
            log.row_count = 0
            log.imported_count = 0
            log.duplicate_count = 0
            await db.commit()
            await db.refresh(log)
            return ImportResult(
                upload_log_id=str(log.id),
                account_id=str(account.id),
                bank_key=adapter.bank_key,
                imported_count=0,
                duplicate_count=0,
                error_count=0,
                status="completed",
                errors=[{"warning": w} for w in warnings],
            )

        imported, duplicates, errors = await _bulk_insert_transactions(
            db, str(account.id), str(log.id), drafts
        )

        log.row_count = len(drafts)
        log.imported_count = imported
        log.duplicate_count = duplicates
        log.error_count = len(errors)

        if errors:
            log.status = "partial" if imported > 0 else "failed"
            log.error_detail = {"errors": errors[:20], "warnings": warnings}
        else:
            log.status = "completed"
            if warnings:
                log.error_detail = {"warnings": warnings}

        # Account 동기화 (최신 잔액/시각)
        last = drafts[-1]
        if last.balance is not None:
            account.current_balance = last.balance
        if last.transaction_date is not None:
            from datetime import datetime as _dt
            from datetime import timezone as _tz

            t = last.transaction_time
            if t is not None:
                account.last_synced_at = _dt.combine(
                    last.transaction_date, t, tzinfo=_tz.utc
                )
            else:
                account.last_synced_at = _dt.combine(
                    last.transaction_date, _dt.min.time(), tzinfo=_tz.utc
                )

        await db.commit()
        await db.refresh(log)

        return ImportResult(
            upload_log_id=str(log.id),
            account_id=str(account.id),
            bank_key=adapter.bank_key,
            imported_count=imported,
            duplicate_count=duplicates,
            error_count=len(errors),
            status=log.status,
            errors=errors,
        )
    finally:
        wb.close()
