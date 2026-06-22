"""playground 라우터 공용 — 서브라우터 팩토리 + 공유 helper 의존성.

각 도메인 모듈은 ``make_router()`` 로 모듈 게이트(require_module)가 걸린
APIRouter 를 만들어 엔드포인트를 등록하고, ``__init__`` 이 그 라우터들을
하나의 ``router`` (prefix=/api/playground) 에 include 한다.

> 모듈 게이트는 최상위 ``router`` 에 한 번만 건다(아래 ``ROUTER_KWARGS``).
> 서브라우터는 prefix/tags 없는 plain APIRouter 로, include 시 합쳐진다.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import require_module
from app.models.playground import PlaygroundAttachment, PlaygroundSession
from app.models.user import User
from app.modules.constants import Module

# 모듈 게이트: 인증 사용자라도 playground 모듈 grant 가 있어야 접근(다른 라우터와 일관).
# admin 전용 통계/세션/로그 엔드포인트는 내부에서 require_admin 으로 추가 보호.
ROUTER_KWARGS = dict(
    prefix="/api/playground",
    tags=["playground"],
    dependencies=[Depends(require_module(Module.PLAYGROUND.value))],
)


def make_subrouter() -> APIRouter:
    """도메인 모듈용 plain 서브라우터. 게이트/prefix 는 최상위에서 일괄 적용."""
    return APIRouter()


async def fetch_session_or_404(
    db: AsyncSession,
    session_id: uuid.UUID,
    user: User,
) -> PlaygroundSession:
    stmt = select(PlaygroundSession).where(PlaygroundSession.id == session_id)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    if str(row.user_id) != str(user.id):
        raise HTTPException(status_code=403, detail="다른 사용자의 세션에 접근할 수 없습니다")
    return row


async def ensure_attachment_is_user_image(
    db: AsyncSession,
    attachment_id: uuid.UUID,
    user: User,
) -> PlaygroundAttachment:
    """베이스 이미지 첨부 검증: 본인 소유 + kind=='image'."""
    row = (
        await db.execute(
            select(PlaygroundAttachment).where(PlaygroundAttachment.id == attachment_id)
        )
    ).scalar_one_or_none()
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="베이스 이미지를 찾을 수 없습니다")
    if row.kind != "image":
        raise HTTPException(
            status_code=400, detail="베이스로는 이미지 파일만 사용할 수 있습니다"
        )
    return row
