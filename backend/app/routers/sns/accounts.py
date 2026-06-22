"""SNS 계정 CRUD + Meta 토큰 진단(admin)."""

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.sns import SocialAccount, SocialPost, SocialWeeklySnapshot
from app.schemas.sns import (
    AccountCreate,
    AccountDeleteResponse,
    AccountRead,
    AccountUpdate,
)

from ._common import router

# ---------------- 계정 ----------------


@router.get("/accounts", response_model=list[AccountRead])
async def list_accounts(
    platform: str | None = Query(None),
    language: str | None = Query(None),
    is_active: bool | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(SocialAccount).order_by(SocialAccount.platform, SocialAccount.language)
    if platform:
        query = query.where(SocialAccount.platform == platform)
    if language:
        query = query.where(SocialAccount.language == language)
    if is_active is not None:
        query = query.where(SocialAccount.is_active == is_active)
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/accounts",
    response_model=AccountRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
)
async def create_account(body: AccountCreate, db: AsyncSession = Depends(get_db)):
    account = SocialAccount(**body.model_dump())
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountRead,
    dependencies=[Depends(require_admin)],
)
async def update_account(account_id: str, body: AccountUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(account, field, value)
    await db.commit()
    await db.refresh(account)
    return account


@router.delete(
    "/accounts/{account_id}",
    response_model=AccountDeleteResponse,
    dependencies=[Depends(require_admin)],
)
async def delete_account(
    account_id: str,
    hard: bool = Query(
        False,
        description="True면 계정과 모든 하위 데이터(게시물·스냅샷·메트릭·댓글)를 영구 삭제. "
        "기본(False)은 소프트삭제(is_active=False)로 수집 이력을 보존한다.",
    ),
    db: AsyncSession = Depends(get_db),
):
    """계정 삭제.

    - 기본(`hard=false`): 소프트삭제 — `is_active=False`로 비활성화하고 모든 이력은 보존한다.
      `PATCH`의 소프트삭제와 동일한 결과이나, 의미가 명확한 전용 엔드포인트.
    - `hard=true`: 영구 삭제 — 계정 행을 실제로 DELETE 한다. FK `ON DELETE CASCADE`로
      하위 SocialPost / SocialWeeklySnapshot (그리고 post에 딸린 metric snapshot·comment)이
      함께 정리된다. **수집된 트렌드/메트릭 이력까지 영구 소실**되므로 호출 측에서 명시적 확인 필요.

    없는 계정이면 404.
    """
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")

    if not hard:
        account.is_active = False
        await db.commit()
        return AccountDeleteResponse(id=account.id, hard=False, deleted=False)

    # 하드삭제: 단일 트랜잭션. CASCADE FK가 metric snapshot·comment를 정리하지만,
    # 삭제 건수를 응답에 담기 위해 posts/snapshots는 명시적으로 카운트 후 삭제한다.
    account_uuid = account.id
    posts_deleted = await db.scalar(
        select(func.count(SocialPost.id)).where(SocialPost.account_id == account_uuid)
    )
    snapshots_deleted = await db.scalar(
        select(func.count(SocialWeeklySnapshot.id)).where(
            SocialWeeklySnapshot.account_id == account_uuid
        )
    )
    # 계정 행 삭제 → CASCADE로 posts(→metrics/comments)·snapshots 동반 삭제.
    await db.delete(account)
    await db.commit()
    return AccountDeleteResponse(
        id=account_uuid,
        hard=True,
        deleted=True,
        posts_deleted=int(posts_deleted or 0),
        snapshots_deleted=int(snapshots_deleted or 0),
    )


# ---------------- Meta 토큰 진단 (admin) ----------------


@router.get("/meta/whoami", dependencies=[Depends(require_admin)])
async def meta_whoami():
    """현재 META_ACCESS_TOKEN 이 무엇이고 어떤 페이지/IG 자산을 볼 수 있는지 진단.

    수집 권한 오류(code 10/100) 원인 파악용. 페이지 토큰은 노출하지 않고 보유 여부만.
    """
    from app.services.sns_collectors.base import CollectorError
    from app.services.sns_collectors.meta_graph import graph_get

    try:
        me = await graph_get("me", params={"fields": "id,name"})
        accounts = await graph_get(
            "me/accounts",
            params={
                "fields": "id,name,tasks,access_token,instagram_business_account"
            },
        )
    except CollectorError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    pages = []
    for p in accounts.get("data") or []:
        ig = p.get("instagram_business_account") or {}
        pages.append(
            {
                "page_id": p.get("id"),
                "name": p.get("name"),
                "tasks": p.get("tasks"),
                "has_page_token": bool(p.get("access_token")),
                "instagram_business_account_id": ig.get("id"),
            }
        )
    return {"me": me, "pages": pages}
