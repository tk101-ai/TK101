"""은행 거래내역 자동 인식 + 계좌 자동 등록 라우터.

엔드포인트:
- ``POST /api/bank-import/preview``  : 파일 1개 → 메타·거래 건수·중복 추정.
- ``POST /api/bank-import/confirm``  : 파일 + (account_id | create_account) → 적재.
- ``GET  /api/bank-import/adapters`` : 지원 은행 목록 (UI 가이드용).

confirm 패턴은 "파일 재전송" — 멱등하고 세션 관리가 필요 없다. 분기당 수십 KB
~수백 KB 수준이므로 대역폭 부담은 무시 가능.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_module
from app.models.user import User
from app.modules.constants import Module
from app.schemas.bank_import import (
    AccountMetaOut,
    ImportConfirmRequest,
    ImportPreviewOut,
    ImportResultOut,
    SimilarAccountOut,
)
from app.services.bank_import import (
    ImportConfirmInput,
    confirm_import,
    get_all_adapters,
    preview_import,
)
from app.services.translation.translator import (
    RateLimitExceeded,
    check_rate_limit,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/bank-import",
    tags=["bank-import"],
    dependencies=[Depends(require_module(Module.FINANCE.value))],
)

MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB (분기 파일은 보통 수백KB)


async def _read_file(file: UploadFile) -> bytes:
    contents = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="파일 크기 초과 (최대 20MB)",
        )
    return contents


@router.get("/adapters")
async def list_adapters(
    _user: User = Depends(get_current_user),
) -> list[dict[str, object]]:
    """지원 은행 목록. UI 에서 셀렉터/도움말 등으로 노출."""
    return [
        {
            "bank_key": a.bank_key,
            "bank_name": a.bank_name,
            "priority": a.priority,
        }
        for a in get_all_adapters()
    ]


@router.post("/preview", response_model=ImportPreviewOut)
async def preview_endpoint(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportPreviewOut:
    # HIGH-10: 분당 10회 (대용량 파싱 비용 큼).
    try:
        check_rate_limit(str(user.id), max_calls=10, window_sec=60)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.",
        ) from exc

    contents = await _read_file(file)
    preview = await preview_import(db, contents, file.filename or "unknown.xlsx")

    meta_out: AccountMetaOut | None = None
    if preview.account_meta is not None:
        meta_out = AccountMetaOut(
            bank_key=preview.account_meta.bank_key,
            bank_name=preview.account_meta.bank_name,
            account_number=preview.account_meta.account_number,
            account_holder=preview.account_meta.account_holder,
            currency=preview.account_meta.currency,
            account_label=preview.account_meta.account_label,
            period_year=preview.account_meta.period_year,
            period_quarter=preview.account_meta.period_quarter,
        )

    return ImportPreviewOut(
        file_name=preview.file_name,
        adapter_detected=preview.adapter_detected,
        bank_name=preview.bank_name,
        account_meta=meta_out,
        existing_account_id=preview.existing_account_id,
        similar_accounts=[
            SimilarAccountOut(
                id=s.id,
                bank_name=s.bank_name,
                account_number=s.account_number,
                account_holder=s.account_holder,
                currency=s.currency,
                account_label=s.account_label,
                score=s.score,
            )
            for s in preview.similar_accounts
        ],
        transaction_count=preview.transaction_count,
        duplicate_count_estimate=preview.duplicate_count_estimate,
        parse_warnings=preview.parse_warnings,
        parse_errors=preview.parse_errors,
    )


@router.post(
    "/confirm",
    response_model=ImportResultOut,
    status_code=status.HTTP_201_CREATED,
)
async def confirm_endpoint(
    file: UploadFile = File(...),
    payload: str = Form(
        ...,
        description=(
            "JSON 문자열. {account_id?, create_account?, on_duplicate?}. "
            "account_id 또는 create_account 중 하나는 필수."
        ),
    ),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ImportResultOut:
    # HIGH-10: confirm 은 DB write 까지 가므로 10회/분 제한.
    try:
        check_rate_limit(str(user.id), max_calls=10, window_sec=60)
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.",
        ) from exc

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"payload JSON 파싱 실패: {e}",
        )

    try:
        req = ImportConfirmRequest.model_validate(parsed)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"payload 검증 실패: {e}",
        )

    if not req.account_id and not req.create_account:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="account_id 또는 create_account 중 하나는 필수입니다",
        )

    contents = await _read_file(file)
    inp = ImportConfirmInput(
        file_bytes=contents,
        file_name=file.filename or "unknown.xlsx",
        user_id=user.id,
        account_id=req.account_id,
        create_account=req.create_account,
        on_duplicate=req.on_duplicate,
    )
    result = await confirm_import(db, inp)
    return ImportResultOut(
        upload_log_id=result.upload_log_id,
        account_id=result.account_id,
        bank_key=result.bank_key,
        imported_count=result.imported_count,
        duplicate_count=result.duplicate_count,
        error_count=result.error_count,
        status=result.status,
        errors=result.errors,
    )
