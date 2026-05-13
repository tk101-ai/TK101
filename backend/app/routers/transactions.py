"""거래(transactions) 라우터 — Wave 2 백엔드 A.

핵심 엔드포인트:
- GET    /api/transactions                           목록 + 필터 + X-Total-Count
- POST   /api/transactions                           수동 거래 등록 (해시 중복 차단)
- PATCH  /api/transactions/{id}                      메타 인라인 편집
- DELETE /api/transactions/{id}                      soft delete (admin)
- POST   /api/transactions/{id}/restore              복구 (admin)
- PATCH  /api/transactions/{id}/memo                 메모 업데이트 (기존 호환)
- GET    /api/transactions/download                  엑셀 다운로드 (기존 호환)
- GET    /api/transactions/monthly-summary           월별 입출금 집계
- GET    /api/transactions/counterparts              거래처 자동완성
- GET    /api/transactions/top-counterparts          상위 거래처 Top N
- GET    /api/transactions/account-balances          계좌별 현재 잔액 카드
- GET    /api/transactions/matching/candidates       매칭 후보 조회
- PATCH  /api/transactions/{id}/match                수동 매칭
- DELETE /api/transactions/{id}/match                매칭 해제

권한:
- 기본: require_module("finance") (라우터 dependency)
- DELETE/restore: require_admin (실수 방지)
- POST/PATCH/GET: finance 모듈 멤버 누구나 가능

설계 메모:
- soft delete: 기본 쿼리에서 is_deleted=False. include_deleted=True 시만 노출.
- transaction_hash: account_id + date + amount + type + balance + description SHA256.
  중복 hash 발견 시 409 Conflict.
- amount/date/transaction_type 변경 금지 (PATCH 에서 거부) — 회계 기록 보존.
- X-Total-Count: list 엔드포인트에서 별도 COUNT 쿼리. 프론트 페이지네이션용.
- 집계 쿼리는 SQLAlchemy `func` 사용. PostgreSQL `date_trunc` 활용.
"""
from __future__ import annotations

import hashlib
import io
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlalchemy import case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_module
from app.models.account import Account
from app.models.counterpart import Counterpart
from app.models.transaction import Transaction
from app.modules.constants import Module
from app.schemas.transaction import (
    AccountBalanceItem,
    CounterpartSuggestion,
    MemoUpdate,
    MonthlySummaryItem,
    TopCounterpartItem,
    TransactionCreate,
    TransactionMatchRequest,
    TransactionRead,
    TransactionUpdate,
)
from app.services import matching as matching_service

router = APIRouter(
    prefix="/api/transactions",
    tags=["transactions"],
    dependencies=[Depends(require_module(Module.FINANCE.value))],
)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _compute_transaction_hash(
    account_id: uuid.UUID | str,
    transaction_date: date,
    amount: Decimal,
    transaction_type: str,
    balance: Decimal | None,
    description: str | None,
) -> str:
    """거래 중복 차단용 SHA256 hex.

    포맷: "{account_id}|{date_iso}|{amount}|{type}|{balance}|{description}"
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


def _build_query(
    account_id: str | None,
    date_from: date | None,
    date_to: date | None,
    transaction_type: str | None,
    match_status: str | None,
    keyword: str | None,
    min_amount: Decimal | None = None,
    max_amount: Decimal | None = None,
    category_id: str | None = None,
    counterpart_id: str | None = None,
    include_deleted: bool = False,
):
    """공통 필터 쿼리 빌더. 모든 라우터에서 동일한 필터 의미 보장."""
    query = select(Transaction).order_by(Transaction.transaction_date.desc())
    if not include_deleted:
        query = query.where(Transaction.is_deleted.is_(False))
    if account_id:
        query = query.where(Transaction.account_id == account_id)
    if date_from:
        query = query.where(Transaction.transaction_date >= date_from)
    if date_to:
        query = query.where(Transaction.transaction_date <= date_to)
    if transaction_type:
        query = query.where(Transaction.transaction_type == transaction_type)
    if match_status:
        query = query.where(Transaction.match_status == match_status)
    if min_amount is not None:
        query = query.where(Transaction.amount >= min_amount)
    if max_amount is not None:
        query = query.where(Transaction.amount <= max_amount)
    if category_id:
        query = query.where(Transaction.category_id == category_id)
    if counterpart_id:
        query = query.where(Transaction.counterpart_id == counterpart_id)
    if keyword:
        like = f"%{keyword}%"
        # counterpart 마스터(name) 도 검색 키워드에 포함.
        cp_subq = select(Counterpart.id).where(Counterpart.name.ilike(like))
        query = query.where(
            or_(
                Transaction.counterpart_name.ilike(like),
                Transaction.description.ilike(like),
                Transaction.memo.ilike(like),
                Transaction.counterpart_id.in_(cp_subq),
            )
        )
    return query


# ---------------------------------------------------------------------------
# LIST + 메모 업데이트 + 다운로드 (기존 호환)
# ---------------------------------------------------------------------------


@router.get("", response_model=list[TransactionRead])
async def list_transactions(
    response: Response,
    account_id: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    transaction_type: str | None = Query(None),
    match_status: str | None = Query(None),
    keyword: str | None = Query(None),
    min_amount: Decimal | None = Query(None),
    max_amount: Decimal | None = Query(None),
    category_id: str | None = Query(None),
    counterpart_id: str | None = Query(None),
    include_deleted: bool = Query(False),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """거래 목록. 응답 헤더 `X-Total-Count` 에 필터 적용 후 총 건수."""
    base_query = _build_query(
        account_id,
        date_from,
        date_to,
        transaction_type,
        match_status,
        keyword,
        min_amount=min_amount,
        max_amount=max_amount,
        category_id=category_id,
        counterpart_id=counterpart_id,
        include_deleted=include_deleted,
    )

    # 총 건수 (필터 적용 후, limit/offset 미적용).
    count_stmt = select(func.count()).select_from(base_query.subquery())
    total_result = await db.execute(count_stmt)
    total = int(total_result.scalar_one() or 0)
    response.headers["X-Total-Count"] = str(total)

    result = await db.execute(base_query.limit(limit).offset(offset))
    return result.scalars().all()


@router.patch("/{transaction_id}/memo", response_model=TransactionRead)
async def update_memo(
    transaction_id: str, body: MemoUpdate, db: AsyncSession = Depends(get_db)
):
    """메모 단독 업데이트 (기존 프론트 호환)."""
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="거래를 찾을 수 없습니다")
    if txn.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="삭제된 거래는 수정할 수 없습니다"
        )
    txn.memo = body.memo
    await db.commit()
    await db.refresh(txn)
    return txn


DOWNLOAD_MAX_ROWS = 50_000


@router.get("/download")
async def download_excel(
    account_id: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    transaction_type: str | None = Query(None),
    match_status: str | None = Query(None),
    keyword: str | None = Query(None),
    min_amount: Decimal | None = Query(None),
    max_amount: Decimal | None = Query(None),
    category_id: str | None = Query(None),
    counterpart_id: str | None = Query(None),
    include_deleted: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    query = _build_query(
        account_id,
        date_from,
        date_to,
        transaction_type,
        match_status,
        keyword,
        min_amount=min_amount,
        max_amount=max_amount,
        category_id=category_id,
        counterpart_id=counterpart_id,
        include_deleted=include_deleted,
    )
    result = await db.execute(query.limit(DOWNLOAD_MAX_ROWS))
    rows = result.scalars().all()

    wb = Workbook()
    ws = wb.active
    ws.title = "거래내역"
    ws.append(["거래일", "구분", "금액", "잔액", "상대방", "적요", "매칭상태", "메모"])
    for r in rows:
        ws.append(
            [
                r.transaction_date.isoformat(),
                r.transaction_type,
                float(r.amount),
                float(r.balance) if r.balance else None,
                r.counterpart_name,
                r.description,
                r.match_status,
                r.memo,
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=transactions.xlsx"},
    )


# ---------------------------------------------------------------------------
# 집계 API
# ---------------------------------------------------------------------------


@router.get("/monthly-summary", response_model=list[MonthlySummaryItem])
async def monthly_summary(
    date_from: date | None = Query(None, alias="from"),
    date_to: date | None = Query(None, alias="to"),
    account_id: str | None = Query(None),
    category_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """월별 입출금 집계.

    응답: [{ month: "YYYY-MM", deposit_total, withdrawal_total, net, count }, ...]
    오름차순 정렬. is_deleted=False 만 집계.
    """
    month_expr = func.to_char(
        func.date_trunc("month", Transaction.transaction_date), "YYYY-MM"
    )
    deposit_sum = func.coalesce(
        func.sum(
            case((Transaction.transaction_type == "deposit", Transaction.amount), else_=0)
        ),
        0,
    )
    withdrawal_sum = func.coalesce(
        func.sum(
            case(
                (Transaction.transaction_type == "withdrawal", Transaction.amount),
                else_=0,
            )
        ),
        0,
    )

    stmt = (
        select(
            month_expr.label("month"),
            deposit_sum.label("deposit_total"),
            withdrawal_sum.label("withdrawal_total"),
            func.count().label("count"),
        )
        .where(Transaction.is_deleted.is_(False))
        .group_by(month_expr)
        .order_by(month_expr.asc())
    )
    if date_from:
        stmt = stmt.where(Transaction.transaction_date >= date_from)
    if date_to:
        stmt = stmt.where(Transaction.transaction_date <= date_to)
    if account_id:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id:
        stmt = stmt.where(Transaction.category_id == category_id)

    result = await db.execute(stmt)
    items: list[MonthlySummaryItem] = []
    for row in result.all():
        deposit_total = Decimal(row.deposit_total or 0)
        withdrawal_total = Decimal(row.withdrawal_total or 0)
        items.append(
            MonthlySummaryItem(
                month=row.month,
                deposit_total=deposit_total,
                withdrawal_total=withdrawal_total,
                net=deposit_total - withdrawal_total,
                count=int(row.count or 0),
            )
        )
    return items


@router.get("/counterparts", response_model=list[CounterpartSuggestion])
async def counterpart_suggestions(
    q: str | None = Query(None, description="이름 부분 일치 (ilike)"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """거래처 자동완성.

    1) counterparts 마스터 검색 (q 부분 일치)
    2) 마스터에 없는 거래의 Transaction.counterpart_name distinct fallback
    두 결과를 합쳐 빈도 순 정렬.
    """
    like = f"%{q}%" if q else "%"

    # 1) 마스터: 각 counterpart_id 와 그에 연결된 거래 건수.
    master_count = func.count(Transaction.id).label("cnt")
    master_stmt = (
        select(Counterpart.id, Counterpart.name, master_count)
        .join(
            Transaction,
            Transaction.counterpart_id == Counterpart.id,
            isouter=True,
        )
        .where(Counterpart.name.ilike(like))
        .group_by(Counterpart.id, Counterpart.name)
        .order_by(master_count.desc(), Counterpart.name.asc())
        .limit(limit)
    )
    master_result = await db.execute(master_stmt)
    suggestions: list[CounterpartSuggestion] = []
    seen_names: set[str] = set()
    for cp_id, cp_name, cnt in master_result.all():
        suggestions.append(
            CounterpartSuggestion(name=cp_name, count=int(cnt or 0), counterpart_id=cp_id)
        )
        seen_names.add(cp_name)
        if len(suggestions) >= limit:
            return suggestions

    # 2) Fallback: 거래 테이블의 raw counterpart_name (마스터 없는 거래).
    remaining = limit - len(suggestions)
    if remaining > 0:
        raw_count = func.count(Transaction.id).label("cnt")
        raw_stmt = (
            select(Transaction.counterpart_name, raw_count)
            .where(Transaction.is_deleted.is_(False))
            .where(Transaction.counterpart_id.is_(None))
            .where(Transaction.counterpart_name.is_not(None))
        )
        if q:
            raw_stmt = raw_stmt.where(Transaction.counterpart_name.ilike(like))
        raw_stmt = (
            raw_stmt.group_by(Transaction.counterpart_name)
            .order_by(raw_count.desc(), Transaction.counterpart_name.asc())
            .limit(remaining)
        )
        raw_result = await db.execute(raw_stmt)
        for name, cnt in raw_result.all():
            if name in seen_names:
                continue
            suggestions.append(
                CounterpartSuggestion(name=name, count=int(cnt or 0), counterpart_id=None)
            )

    return suggestions


@router.get("/top-counterparts", response_model=list[TopCounterpartItem])
async def top_counterparts(
    period_from: date | None = Query(None),
    period_to: date | None = Query(None),
    transaction_type: str | None = Query(
        None, alias="type", pattern=r"^(deposit|withdrawal)$"
    ),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """상위 거래처 Top N (금액 기준).

    GROUP BY 우선순위: counterpart_id 있으면 그 기준, 없으면 counterpart_name.
    응답 정렬: SUM(amount) desc.
    """
    total_amount = func.sum(Transaction.amount).label("total_amount")
    item_count = func.count().label("cnt")
    # 이름 표시: 마스터 join 우선, 없으면 raw counterpart_name.
    display_name = func.coalesce(Counterpart.name, Transaction.counterpart_name).label(
        "display_name"
    )
    stmt = (
        select(
            display_name,
            Counterpart.id.label("cp_id"),
            total_amount,
            item_count,
        )
        .join(
            Counterpart,
            Counterpart.id == Transaction.counterpart_id,
            isouter=True,
        )
        .where(Transaction.is_deleted.is_(False))
        .group_by(Counterpart.id, Counterpart.name, Transaction.counterpart_name)
        .order_by(total_amount.desc())
        .limit(limit)
    )
    if period_from:
        stmt = stmt.where(Transaction.transaction_date >= period_from)
    if period_to:
        stmt = stmt.where(Transaction.transaction_date <= period_to)
    if transaction_type:
        stmt = stmt.where(Transaction.transaction_type == transaction_type)

    result = await db.execute(stmt)
    items: list[TopCounterpartItem] = []
    for row in result.all():
        name = row.display_name
        if not name:
            # null 그룹은 노이즈. 스킵.
            continue
        items.append(
            TopCounterpartItem(
                counterpart_name=name,
                counterpart_id=row.cp_id,
                total_amount=Decimal(row.total_amount or 0),
                count=int(row.cnt or 0),
            )
        )
    return items


@router.get("/account-balances", response_model=list[AccountBalanceItem])
async def account_balances(db: AsyncSession = Depends(get_db)):
    """계좌별 현재 잔액 카드 데이터.

    current_balance 캐시 우선, 없으면 가장 최근 거래의 balance 로 fallback.

    HIGH-9 fix: 루프 안 개별 쿼리 → PostgreSQL DISTINCT ON 으로 일괄 조회.
    각 account_id 별 (transaction_date DESC, created_at DESC) 첫 번째 row 의 balance/date 를 얻는다.
    """
    accounts_result = await db.execute(
        select(Account)
        .where(Account.is_active.is_(True))
        .order_by(Account.bank_name.asc())
    )
    accounts = list(accounts_result.scalars().all())

    # DISTINCT ON (account_id) — PostgreSQL 전용. 각 계좌의 가장 최근 활성 거래 1건.
    latest_stmt = (
        select(
            Transaction.account_id,
            Transaction.transaction_date,
            Transaction.balance,
        )
        .where(Transaction.is_deleted.is_(False))
        .order_by(
            Transaction.account_id,
            Transaction.transaction_date.desc(),
            Transaction.created_at.desc(),
        )
        .distinct(Transaction.account_id)
    )
    latest_result = await db.execute(latest_stmt)
    # account_id → (last_date, last_balance)
    latest_by_account: dict[str, tuple[date, Decimal | None]] = {}
    for row in latest_result.all():
        latest_by_account[str(row.account_id)] = (
            row.transaction_date,
            row.balance,
        )

    items: list[AccountBalanceItem] = []
    for acc in accounts:
        latest = latest_by_account.get(str(acc.id))
        last_date = latest[0] if latest else None
        current = acc.current_balance
        if current is None and latest is not None:
            current = latest[1]

        items.append(
            AccountBalanceItem(
                account_id=acc.id,
                bank_name=acc.bank_name,
                account_number=acc.account_number,
                account_type=acc.account_type,
                currency=acc.currency or "KRW",
                current_balance=current,
                last_synced_at=acc.last_synced_at,
                last_transaction_date=last_date,
            )
        )
    return items


# ---------------------------------------------------------------------------
# 매칭 워크북
# ---------------------------------------------------------------------------


@router.get("/matching/candidates", response_model=list[TransactionRead])
async def matching_candidates(
    transaction_id: str = Query(..., description="기준 거래 ID"),
    window_days: int = Query(7, ge=0, le=60),
    db: AsyncSession = Depends(get_db),
):
    """수동 매칭 후보 거래 목록."""
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    tx = result.scalar_one_or_none()
    if tx is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="거래를 찾을 수 없습니다")
    if tx.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="삭제된 거래는 매칭할 수 없습니다"
        )
    return await matching_service.find_match_candidates(db, tx, window_days=window_days)


@router.patch("/{transaction_id}/match", response_model=TransactionRead)
async def manual_match(
    transaction_id: str,
    body: TransactionMatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """두 거래를 manual 매칭."""
    try:
        a, _b = await matching_service.apply_manual_match(
            db, transaction_id, body.matched_transaction_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    # HIGH-8: 서비스는 flush 만 함. 라우터에서 명시 커밋.
    await db.commit()
    return a


@router.delete("/{transaction_id}/match", response_model=TransactionRead)
async def unmatch(transaction_id: str, db: AsyncSession = Depends(get_db)):
    """매칭 해제 — 양방향 unmatched."""
    try:
        tx = await matching_service.remove_match(db, transaction_id)
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    # HIGH-8: 서비스는 flush 만 함. 라우터에서 명시 커밋.
    await db.commit()
    return tx


# ---------------------------------------------------------------------------
# CRUD (수동 등록 / 인라인 편집 / soft delete / restore)
# ---------------------------------------------------------------------------


@router.post(
    "",
    response_model=TransactionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_transaction(
    body: TransactionCreate,
    db: AsyncSession = Depends(get_db),
):
    """수동 거래 등록. 해시 중복 시 409."""
    # 계좌 존재 확인.
    acc_result = await db.execute(select(Account).where(Account.id == body.account_id))
    account = acc_result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계좌를 찾을 수 없습니다")

    tx_hash = _compute_transaction_hash(
        body.account_id,
        body.transaction_date,
        body.amount,
        body.transaction_type,
        body.balance,
        body.description,
    )

    # 동일 (account_id, transaction_hash) 중복 차단.
    dup_result = await db.execute(
        select(Transaction.id)
        .where(Transaction.account_id == body.account_id)
        .where(Transaction.transaction_hash == tx_hash)
        .where(Transaction.is_deleted.is_(False))
        .limit(1)
    )
    if dup_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="동일한 거래가 이미 등록되어 있습니다 (해시 충돌)",
        )

    txn = Transaction(
        account_id=body.account_id,
        transaction_date=body.transaction_date,
        amount=body.amount,
        balance=body.balance,
        counterpart_name=body.counterpart_name,
        description=body.description,
        transaction_type=body.transaction_type,
        match_status="unmatched",
        memo=body.memo,
        transaction_hash=tx_hash,
        category_id=body.category_id,
        counterpart_id=body.counterpart_id,
        tags=body.tags,
        is_deleted=False,
    )
    db.add(txn)
    await db.flush()

    # Account.current_balance / last_synced_at 업데이트 (마지막 거래일 기준).
    if account.last_synced_at is None or body.transaction_date >= (
        account.last_synced_at.date()
        if isinstance(account.last_synced_at, datetime)
        else account.last_synced_at
    ):
        if body.balance is not None:
            account.current_balance = body.balance
        account.last_synced_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(txn)
    return txn


@router.patch("/{transaction_id}", response_model=TransactionRead)
async def update_transaction(
    transaction_id: str,
    body: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
):
    """거래 메타 인라인 편집.

    허용 필드: category_id, counterpart_id, counterpart_name, memo, tags, description.
    금지: amount, transaction_date, transaction_type (회계 기록 보존).
    """
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="거래를 찾을 수 없습니다")
    if txn.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="삭제된 거래는 수정할 수 없습니다"
        )

    # exclude_unset: 클라이언트가 보낸 필드만 갱신 (null 명시도 허용).
    payload = body.model_dump(exclude_unset=True)
    for field, value in payload.items():
        setattr(txn, field, value)

    await db.commit()
    await db.refresh(txn)
    return txn


@router.delete(
    "/{transaction_id}",
    response_model=TransactionRead,
    dependencies=[Depends(require_admin)],
)
async def soft_delete_transaction(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Soft delete — is_deleted=True. 실제 row 보존. 관리자 전용."""
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="거래를 찾을 수 없습니다")
    if txn.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 삭제된 거래입니다"
        )
    txn.is_deleted = True
    # 매칭 상태 정리: 삭제되는 거래는 매칭 끊기.
    if txn.matched_transaction_id is not None:
        partner_result = await db.execute(
            select(Transaction).where(Transaction.id == txn.matched_transaction_id)
        )
        partner = partner_result.scalar_one_or_none()
        if partner is not None:
            partner.matched_transaction_id = None
            partner.match_status = "unmatched"
        txn.matched_transaction_id = None
        txn.match_status = "unmatched"

    await db.commit()
    await db.refresh(txn)
    return txn


@router.post(
    "/{transaction_id}/restore",
    response_model=TransactionRead,
    dependencies=[Depends(require_admin)],
)
async def restore_transaction(
    transaction_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Soft delete 복구. 관리자 전용. 매칭 상태는 복구하지 않음."""
    result = await db.execute(
        select(Transaction).where(Transaction.id == transaction_id)
    )
    txn = result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="거래를 찾을 수 없습니다")
    if not txn.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 활성 상태인 거래입니다"
        )
    txn.is_deleted = False
    await db.commit()
    await db.refresh(txn)
    return txn
