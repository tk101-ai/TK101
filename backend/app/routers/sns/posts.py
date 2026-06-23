"""SNS 게시물(Post) CRUD · 주간 스냅샷 · 수동 콘텐츠 등록 · 게시물 초기화."""

from datetime import date

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.sns import SocialAccount, SocialPost, SocialWeeklySnapshot
from app.schemas.sns import (
    ContentCreate,
    PostCreate,
    PostRead,
    PostUpdate,
    SnapshotCreate,
    SnapshotRead,
)
from app.services.sns_collection import upsert_snapshot

from ._common import router

# ---------------- 콘텐츠 (Post) ----------------


@router.get("/posts", response_model=list[PostRead])
async def list_posts(
    account_id: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    content_type: str | None = Query(None),
    category: str | None = Query(None),
    language: str | None = Query(None),
    platform: str | None = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    query = select(SocialPost).order_by(SocialPost.posted_at.desc())
    if account_id:
        query = query.where(SocialPost.account_id == account_id)
    if date_from:
        query = query.where(SocialPost.posted_at >= date_from)
    if date_to:
        query = query.where(SocialPost.posted_at <= date_to)
    if content_type:
        query = query.where(SocialPost.content_type == content_type)
    if category:
        query = query.where(SocialPost.category == category)
    if language or platform:
        query = query.join(SocialAccount, SocialAccount.id == SocialPost.account_id)
        if language:
            query = query.where(SocialAccount.language == language)
        if platform:
            query = query.where(SocialAccount.platform == platform)
    result = await db.execute(query.limit(limit).offset(offset))
    return result.scalars().all()


@router.post("/posts", response_model=PostRead, status_code=status.HTTP_201_CREATED)
async def create_post(body: PostCreate, db: AsyncSession = Depends(get_db)):
    post = SocialPost(**body.model_dump())
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


@router.patch("/posts/{post_id}", response_model=PostRead)
async def update_post(post_id: str, body: PostUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(SocialPost).where(SocialPost.id == post_id))
    post = result.scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="게시물을 찾을 수 없습니다")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(post, field, value)
    await db.commit()
    await db.refresh(post)
    return post


# ---------------- 주간 스냅샷 ----------------


@router.get("/snapshots", response_model=list[SnapshotRead])
async def list_snapshots(
    account_id: str | None = Query(None),
    year: int | None = Query(None),
    month: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    query = select(SocialWeeklySnapshot).order_by(
        SocialWeeklySnapshot.year.desc(),
        SocialWeeklySnapshot.month.desc(),
        SocialWeeklySnapshot.week_number.desc(),
    )
    if account_id:
        query = query.where(SocialWeeklySnapshot.account_id == account_id)
    if year is not None:
        query = query.where(SocialWeeklySnapshot.year == year)
    if month is not None:
        query = query.where(SocialWeeklySnapshot.month == month)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/snapshots", response_model=SnapshotRead, status_code=status.HTTP_201_CREATED)
async def create_snapshot(body: SnapshotCreate, db: AsyncSession = Depends(get_db)):
    snap, _ = await upsert_snapshot(db, body)
    await db.commit()
    await db.refresh(snap)
    return snap


@router.post("/snapshots/bulk", response_model=list[SnapshotRead])
async def bulk_snapshots(body: list[SnapshotCreate], db: AsyncSession = Depends(get_db)):
    saved: list[SocialWeeklySnapshot] = []
    for item in body:
        snap, _ = await upsert_snapshot(db, item)
        saved.append(snap)
    await db.commit()
    for s in saved:
        await db.refresh(s)
    return saved


# ---------------- 수동 콘텐츠 등록 (FALLBACK 모드) ----------------


@router.post(
    "/accounts/{account_id}/contents",
    response_model=PostRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_content(
    account_id: str,
    body: ContentCreate,
    db: AsyncSession = Depends(get_db),
):
    """수동 콘텐츠 1행 등록 (배포일/제목/형태/제작주체/URL). is_manual=true.

    메타 토큰이 없어도 동작하는 FALLBACK 경로. 등록 후 collect-metrics 가
    조회수/좋아요/댓글/공유를 일/주 주기로 채운다.
    """
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")

    post = SocialPost(
        account_id=account.id,
        posted_at=body.posted_at,
        title=body.title,
        content_type=body.content_type,
        producer=body.producer,
        category=body.category.value if body.category else None,
        url=body.url,
        external_id=body.external_id,
        is_manual=True,
    )
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return post


@router.delete(
    "/accounts/{account_id}/posts",
    dependencies=[Depends(require_admin)],
    status_code=status.HTTP_200_OK,
)
async def reset_account_posts(account_id: str, db: AsyncSession = Depends(get_db)):
    """해당 계정의 모든 콘텐츠를 삭제. 주간 팔로워 스냅샷은 보존.

    엑셀 import 데이터를 비우고 자동 수집 결과로 다시 채우려는 케이스 등에 사용.
    """
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")
    delete_result = await db.execute(
        delete(SocialPost).where(SocialPost.account_id == account_id)
    )
    deleted = delete_result.rowcount or 0
    await db.commit()
    return {"deleted": deleted}
