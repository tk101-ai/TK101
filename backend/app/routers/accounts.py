from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin, require_module
from app.models.account import Account
from app.models.transaction import Transaction
from app.models.upload_log import UploadLog
from app.modules.constants import Module
from app.schemas.account import AccountCreate, AccountRead, AccountUpdate

router = APIRouter(
    prefix="/api/accounts",
    tags=["accounts"],
    dependencies=[Depends(require_module(Module.FINANCE.value))],
)


@router.get("", response_model=list[AccountRead])
async def list_accounts(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).order_by(Account.bank_name))
    return result.scalars().all()


@router.post(
    "",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    # 생성은 금융팀 member 도 가능(라우터의 require_module(FINANCE) 게이트로 충분).
    # 수정(PATCH)/삭제(DELETE)는 마스터데이터 보호를 위해 admin 유지.
)
async def create_account(body: AccountCreate, db: AsyncSession = Depends(get_db)):
    account = Account(**body.model_dump())
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@router.patch("/{account_id}", response_model=AccountRead, dependencies=[Depends(require_admin)])
async def update_account(account_id: str, body: AccountUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    await db.commit()
    await db.refresh(account)
    return account


@router.delete(
    "/{account_id}",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_admin)],
)
async def delete_account(
    account_id: str,
    force: bool = Query(False, description="true면 거래내역도 함께 삭제 (CASCADE)"),
    db: AsyncSession = Depends(get_db),
):
    """계좌 hard delete.

    - 거래 0건: 즉시 삭제.
    - 거래 있음: ``force=true`` 없으면 409 + 거래 카운트 반환.
    - ``force=true``: 거래 hard delete + UploadLog.account_id를 NULL로 (audit log 보존).

    FK 정책이 RESTRICT라 application-level cascade를 수행. 마이그레이션 추가 없음.
    """
    result = await db.execute(select(Account).where(Account.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계좌를 찾을 수 없습니다")

    # 거래 카운트
    count_res = await db.execute(
        select(func.count(Transaction.id)).where(Transaction.account_id == account_id)
    )
    tx_count = int(count_res.scalar() or 0)

    if tx_count > 0 and not force:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"이 계좌에 거래내역 {tx_count}건이 있어 삭제할 수 없습니다. "
                f"거래내역까지 함께 삭제하려면 ?force=true 옵션을 사용하세요."
            ),
        )

    if tx_count > 0:
        # 거래 hard delete
        await db.execute(delete(Transaction).where(Transaction.account_id == account_id))

    # UploadLog는 audit 보존 — account_id만 NULL로
    await db.execute(
        update(UploadLog)
        .where(UploadLog.account_id == account_id)
        .values(account_id=None)
    )

    await db.delete(account)
    await db.commit()
    return {"deleted": True, "account_id": account_id, "transactions_deleted": tx_count}
