"""관리자 — 사용량 대시보드 / 전 사용자 세션·메시지 / 한도 관리 / 백엔드 로그 / 미디어 정리.

모든 엔드포인트는 ``require_admin`` 으로 추가 보호 (모듈 게이트 위에).
"""
from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import require_admin
from app.models.playground import PlaygroundMedia, PlaygroundMessage, PlaygroundSession
from app.models.user import User
from app.schemas.playground import (
    PlaygroundAdminQuotaUpdate,
    PlaygroundAdminSessionOut,
    PlaygroundAdminUserQuotaOut,
    PlaygroundMediaCleanupOut,
    PlaygroundMessageOut,
    PlaygroundUsageByModel,
    PlaygroundUsageByUser,
    PlaygroundUsageReport,
)
from app.services.playground.media_cleanup import cleanup_expired_media
from app.services.playground.usage_check import get_user_usage_summary

from ._common import make_subrouter

logger = logging.getLogger(__name__)

router: APIRouter = make_subrouter()


@router.get("/admin/aigc-monitor")
async def admin_aigc_monitor_endpoint(
    days: int = Query(default=14, ge=1, le=90),
    _: User = Depends(require_admin),
) -> dict:
    """텐센트 AIGC 게이트웨이 사용량·Quota 모니터(Text/Image/Video). admin 전용.

    내부 DB 사용량(/admin/usage)과 별개로, 텐센트 측 집계(DescribeAigcUsageData)와
    한도(DescribeAigcQuotas)를 직접 조회한다.
    """
    from app.services.playground.aigc_monitor import get_overview

    return await get_overview(days=days)


@router.get("/admin/usage", response_model=PlaygroundUsageReport)
async def admin_usage_endpoint(
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> PlaygroundUsageReport:
    """모델별·사용자별 사용량 + 비용. admin 전용.

    텍스트는 playground_messages, 이미지/영상은 playground_media 에서 집계.
    """
    # --- 텍스트 (메시지 단위) ---
    msg_stmt = (
        select(
            PlaygroundMessage.model.label("model"),
            func.count().label("count"),
            func.coalesce(func.sum(PlaygroundMessage.input_tokens), 0).label("input"),
            func.coalesce(func.sum(PlaygroundMessage.output_tokens), 0).label("output"),
            func.coalesce(func.sum(PlaygroundMessage.cost_usd), 0).label("cost"),
        )
        .where(PlaygroundMessage.role == "assistant")
        .group_by(PlaygroundMessage.model)
    )
    if start:
        msg_stmt = msg_stmt.where(PlaygroundMessage.created_at >= start)
    if end:
        msg_stmt = msg_stmt.where(PlaygroundMessage.created_at <= end)

    by_model: list[PlaygroundUsageByModel] = []
    total_cost = Decimal(0)
    total_requests = 0
    for row in (await db.execute(msg_stmt)).all():
        if row.model is None:
            continue
        by_model.append(
            PlaygroundUsageByModel(
                model=row.model,
                kind="text",
                request_count=int(row.count),
                input_tokens=int(row.input or 0),
                output_tokens=int(row.output or 0),
                cost_usd=Decimal(row.cost or 0),
            )
        )
        total_cost += Decimal(row.cost or 0)
        total_requests += int(row.count)

    # --- 미디어 (이미지/영상) ---
    media_stmt = (
        select(
            PlaygroundMedia.model_key.label("model"),
            PlaygroundMedia.media_type.label("kind"),
            func.count().label("count"),
            func.coalesce(func.sum(PlaygroundMedia.cost_usd), 0).label("cost"),
        )
        .where(PlaygroundMedia.status == "succeeded")
        .group_by(PlaygroundMedia.model_key, PlaygroundMedia.media_type)
    )
    if start:
        media_stmt = media_stmt.where(PlaygroundMedia.created_at >= start)
    if end:
        media_stmt = media_stmt.where(PlaygroundMedia.created_at <= end)

    for row in (await db.execute(media_stmt)).all():
        if row.model is None:
            continue
        by_model.append(
            PlaygroundUsageByModel(
                model=row.model,
                kind=row.kind or "image",
                request_count=int(row.count),
                input_tokens=0,
                output_tokens=0,
                cost_usd=Decimal(row.cost or 0),
            )
        )
        total_cost += Decimal(row.cost or 0)
        total_requests += int(row.count)

    # --- 사용자별 집계 ---
    user_stmt = (
        select(
            User.id.label("uid"),
            User.email.label("email"),
            func.coalesce(func.sum(PlaygroundMessage.input_tokens), 0).label("input"),
            func.coalesce(func.sum(PlaygroundMessage.output_tokens), 0).label("output"),
            func.coalesce(func.sum(PlaygroundMessage.cost_usd), 0).label("cost"),
            func.count(PlaygroundMessage.id).label("count"),
        )
        .join(PlaygroundSession, PlaygroundSession.user_id == User.id)
        .join(PlaygroundMessage, PlaygroundMessage.session_id == PlaygroundSession.id)
        .where(PlaygroundMessage.role == "assistant")
        .group_by(User.id, User.email)
    )
    if start:
        user_stmt = user_stmt.where(PlaygroundMessage.created_at >= start)
    if end:
        user_stmt = user_stmt.where(PlaygroundMessage.created_at <= end)

    by_user: list[PlaygroundUsageByUser] = []
    for row in (await db.execute(user_stmt)).all():
        by_user.append(
            PlaygroundUsageByUser(
                user_id=row.uid,
                user_email=row.email,
                request_count=int(row.count),
                input_tokens=int(row.input or 0),
                output_tokens=int(row.output or 0),
                cost_usd=Decimal(row.cost or 0),
            )
        )

    # 사용자별 미디어 비용도 합산.
    user_media_stmt = (
        select(
            PlaygroundMedia.user_id.label("uid"),
            func.coalesce(func.sum(PlaygroundMedia.cost_usd), 0).label("cost"),
            func.count().label("count"),
        )
        .where(PlaygroundMedia.status == "succeeded")
        .group_by(PlaygroundMedia.user_id)
    )
    if start:
        user_media_stmt = user_media_stmt.where(PlaygroundMedia.created_at >= start)
    if end:
        user_media_stmt = user_media_stmt.where(PlaygroundMedia.created_at <= end)
    media_by_user = {row.uid: (Decimal(row.cost or 0), int(row.count)) for row in (await db.execute(user_media_stmt)).all()}
    for u in by_user:
        if u.user_id in media_by_user:
            extra_cost, extra_count = media_by_user.pop(u.user_id)
            u.cost_usd = (u.cost_usd or Decimal(0)) + extra_cost
            u.request_count += extra_count
    # 메시지 history 가 없는데 미디어만 만든 사용자 보강.
    if media_by_user:
        leftover_stmt = select(User.id, User.email).where(User.id.in_(media_by_user.keys()))
        for uid, email in (await db.execute(leftover_stmt)).all():
            cost, cnt = media_by_user[uid]
            by_user.append(
                PlaygroundUsageByUser(
                    user_id=uid,
                    user_email=email,
                    request_count=cnt,
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=cost,
                )
            )

    return PlaygroundUsageReport(
        period_start=start,
        period_end=end,
        total_cost_usd=total_cost,
        total_requests=total_requests,
        by_model=sorted(by_model, key=lambda r: r.cost_usd, reverse=True),
        by_user=sorted(by_user, key=lambda r: r.cost_usd, reverse=True),
    )


@router.get(
    "/admin/sessions",
    response_model=list[PlaygroundAdminSessionOut],
)
async def admin_list_sessions_endpoint(
    user_id: uuid.UUID | None = Query(default=None),
    q: str | None = Query(default=None, description="제목/메시지 ILIKE"),
    limit: int = Query(default=50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[PlaygroundAdminSessionOut]:
    """모든 사용자 세션 list. user_id / q 필터, JOIN users 로 email 포함."""
    stmt = (
        select(
            PlaygroundSession.id.label("id"),
            PlaygroundSession.user_id.label("user_id"),
            User.email.label("user_email"),
            PlaygroundSession.title.label("title"),
            PlaygroundSession.provider.label("provider"),
            PlaygroundSession.model.label("model"),
            PlaygroundSession.created_at.label("created_at"),
            PlaygroundSession.updated_at.label("updated_at"),
        )
        .join(User, User.id == PlaygroundSession.user_id)
        .order_by(PlaygroundSession.created_at.desc())
        .limit(limit)
    )
    if user_id is not None:
        stmt = stmt.where(PlaygroundSession.user_id == user_id)
    if q:
        pattern = f"%{q}%"
        msg_subq = (
            select(PlaygroundMessage.session_id)
            .where(PlaygroundMessage.content.ilike(pattern))
            .distinct()
        )
        stmt = stmt.where(
            (PlaygroundSession.title.ilike(pattern))
            | (PlaygroundSession.id.in_(msg_subq))
        )
    rows = (await db.execute(stmt)).all()
    return [
        PlaygroundAdminSessionOut(
            id=r.id,
            user_id=r.user_id,
            user_email=r.user_email,
            title=r.title,
            provider=r.provider,
            model=r.model,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in rows
    ]


@router.get(
    "/admin/sessions/{session_id}/messages",
    response_model=list[PlaygroundMessageOut],
)
async def admin_list_session_messages_endpoint(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[PlaygroundMessageOut]:
    """관리자: 임의 세션의 메시지 전체 (본인 체크 없이)."""
    # 세션 존재 확인.
    exists_stmt = select(PlaygroundSession.id).where(PlaygroundSession.id == session_id)
    if (await db.execute(exists_stmt)).scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")

    stmt = (
        select(PlaygroundMessage)
        .where(PlaygroundMessage.session_id == session_id)
        .order_by(PlaygroundMessage.created_at.asc())
    )
    rows = (await db.execute(stmt)).scalars().all()
    return [PlaygroundMessageOut.model_validate(r) for r in rows]


@router.get(
    "/admin/users/quota",
    response_model=list[PlaygroundAdminUserQuotaOut],
)
async def admin_list_users_quota_endpoint(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> list[PlaygroundAdminUserQuotaOut]:
    """전 사용자별 quota + 이번 월 사용량 list."""
    users_stmt = select(User).where(User.is_active == True).order_by(User.email.asc())  # noqa: E712
    users = (await db.execute(users_stmt)).scalars().all()

    results: list[PlaygroundAdminUserQuotaOut] = []
    for u in users:
        summary = await get_user_usage_summary(db, u.id)
        results.append(
            PlaygroundAdminUserQuotaOut(
                user_id=u.id,
                user_email=u.email,
                user_name=u.name,
                department=u.department,
                role=u.role,
                monthly_quota_usd=summary["monthly_quota_usd"],
                current_usage_usd=summary["current_usage_usd"],
                remaining_usd=summary["remaining_usd"],
            )
        )
    return results


@router.put(
    "/admin/users/{target_user_id}/quota",
    response_model=PlaygroundAdminUserQuotaOut,
)
async def admin_update_user_quota_endpoint(
    target_user_id: uuid.UUID,
    body: PlaygroundAdminQuotaUpdate,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> PlaygroundAdminUserQuotaOut:
    """사용자 월 한도 변경."""
    target = (
        await db.execute(select(User).where(User.id == target_user_id))
    ).scalar_one_or_none()
    if target is None:
        raise HTTPException(status_code=404, detail="사용자를 찾을 수 없습니다")

    target.monthly_quota_usd = body.monthly_quota_usd
    await db.commit()
    await db.refresh(target)

    summary = await get_user_usage_summary(db, target.id)
    return PlaygroundAdminUserQuotaOut(
        user_id=target.id,
        user_email=target.email,
        user_name=target.name,
        department=target.department,
        role=target.role,
        monthly_quota_usd=summary["monthly_quota_usd"],
        current_usage_usd=summary["current_usage_usd"],
        remaining_usd=summary["remaining_usd"],
    )


@router.get("/admin/logs")
async def admin_tail_logs_endpoint(
    tail: int = Query(default=200, ge=1, le=10_000),
    _: User = Depends(require_admin),
) -> StreamingResponse:
    """백엔드 로그 파일의 마지막 N 줄을 text/plain 으로 반환.

    파일이 없으면 빈 응답. 큰 파일 안전을 위해 deque 로 끝에서만 읽음.
    """
    log_path = settings.playground_log_path
    body_text: str
    if not os.path.exists(log_path):
        body_text = ""
    else:
        from collections import deque

        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                last_lines = deque(fh, maxlen=tail)
            body_text = "".join(last_lines)
        except OSError as exc:
            logger.warning("admin logs tail 실패: %s", exc)
            raise HTTPException(status_code=503, detail="로그 파일 읽기 실패") from exc

    async def _gen():
        yield body_text.encode("utf-8")

    return StreamingResponse(_gen(), media_type="text/plain; charset=utf-8")


@router.post("/admin/media/cleanup", response_model=PlaygroundMediaCleanupOut)
async def admin_cleanup_media_endpoint(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> PlaygroundMediaCleanupOut:
    """보존기간(playground_media_retention_days) 경과 미디어 정리.

    디스크 파일 unlink + DB row 삭제. 수동 트리거(admin). lifespan 주기 태스크와
    동일한 ``cleanup_expired_media`` 를 호출한다.
    """
    result = await cleanup_expired_media(db)
    return PlaygroundMediaCleanupOut(
        scanned=result["scanned"],
        deleted_rows=result["deleted_rows"],
        deleted_files=result["deleted_files"],
        file_errors=result["file_errors"],
        retention_days=settings.playground_media_retention_days,
        cutoff=result["cutoff"],
    )
