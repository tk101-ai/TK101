"""AI Playground 라우터.

엔드포인트 (요약):
| 메서드 | 경로                                            | 권한          | 설명                       |
|--------|-------------------------------------------------|---------------|----------------------------|
| GET    | /api/playground/providers                       | 로그인        | LLM provider/모델 chip     |
| GET    | /api/playground/media-models                    | 로그인        | 이미지/영상 모델 카탈로그  |
| POST   | /api/playground/sessions                        | 로그인        | 빈 세션 생성               |
| GET    | /api/playground/sessions                        | 로그인        | 본인 세션 목록             |
| GET    | /api/playground/sessions/{id}/messages          | 로그인 (본인) | 세션 메시지 전체           |
| DELETE | /api/playground/sessions/{id}                   | 로그인 (본인) | 세션 hard delete           |
| POST   | /api/playground/chat                            | 로그인        | SSE 스트리밍 채팅          |
| POST   | /api/playground/image                           | 로그인        | 이미지 task 생성           |
| POST   | /api/playground/video                           | 로그인        | 영상 task 생성             |
| GET    | /api/playground/tasks/{kind}/{task_id}          | 로그인        | 미디어 task 폴링           |
| GET    | /api/playground/media                           | 로그인 (본인) | 본인 미디어 목록 (갤러리)  |
| GET    | /api/playground/media/{id}/file                 | 로그인 (본인) | 미디어 파일 서빙           |
| GET    | /api/playground/admin/usage                     | **admin**     | 모델별/사용자별 사용량     |

2026-05-19 변경:
- admin only 라우터 의존성 제거 → 일반 사용자가 사용은 가능, 통계는 admin 전용.
- 이미지/영상 task 는 생성 시점에 playground_media row 만들고 폴링 시 업데이트.
- 폴링이 succeeded 받으면 텐센트 임시 URL 을 백엔드 디스크로 다운로드 + cost_usd 계산.
- 단가표 적용 (services/playground/pricing.py).
"""
from __future__ import annotations

import json
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.playground import PlaygroundMedia, PlaygroundMessage, PlaygroundSession
from app.models.user import User
from app.schemas.playground import (
    PlaygroundChatRequest,
    PlaygroundImageRequest,
    PlaygroundMediaModelOption,
    PlaygroundMediaOut,
    PlaygroundMessageOut,
    PlaygroundProviderMeta,
    PlaygroundSessionCreate,
    PlaygroundSessionOut,
    PlaygroundTaskCreated,
    PlaygroundTaskStatus,
    PlaygroundUsageByModel,
    PlaygroundUsageByUser,
    PlaygroundUsageReport,
    PlaygroundVideoRequest,
)
from app.services.playground import (
    PROVIDER_CHIPS,
    append_message,
    create_session,
    list_sessions,
    stream_chat,
    update_metrics,
)
from app.services.playground.media_downloader import download_media
from app.services.playground.pricing import (
    calc_image_cost,
    calc_text_cost,
    calc_video_cost,
)
from app.services.playground.session_manager import mask_request_payload
from app.services.playground.tencent_aigc_media import (
    IMAGE_MODELS,
    VIDEO_MODELS,
    create_image_task,
    create_video_task,
    describe_image_task,
    parse_model_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/playground", tags=["playground"])


# ===========================================================================
# 메타 — 로그인만 필요
# ===========================================================================


@router.get("/providers", response_model=list[PlaygroundProviderMeta])
async def get_providers(
    user: User = Depends(get_current_user),
) -> list[PlaygroundProviderMeta]:
    return [PlaygroundProviderMeta.model_validate(p) for p in PROVIDER_CHIPS]


@router.get("/media-models")
async def list_media_models(
    user: User = Depends(get_current_user),
) -> dict[str, list[PlaygroundMediaModelOption]]:
    return {
        "image": [
            PlaygroundMediaModelOption(key=m["key"], label=m["label"], badge=m["badge"] or None)
            for m in IMAGE_MODELS
        ],
        "video": [
            PlaygroundMediaModelOption(key=m["key"], label=m["label"], badge=m["badge"] or None)
            for m in VIDEO_MODELS
        ],
    }


# ===========================================================================
# 세션
# ===========================================================================


@router.post(
    "/sessions",
    response_model=PlaygroundSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_endpoint(
    body: PlaygroundSessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundSessionOut:
    row = await create_session(
        db,
        user_id=user.id,
        provider=body.provider,
        model=body.model,
        title=body.title,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
    )
    return PlaygroundSessionOut.model_validate(row)


@router.get("/sessions", response_model=list[PlaygroundSessionOut])
async def list_sessions_endpoint(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PlaygroundSessionOut]:
    rows = await list_sessions(db, user_id=user.id)
    return [PlaygroundSessionOut.model_validate(r) for r in rows]


@router.get("/sessions/{session_id}/messages", response_model=list[PlaygroundMessageOut])
async def list_messages_endpoint(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PlaygroundMessageOut]:
    session = await _fetch_session_or_404(db, session_id, user)
    stmt = (
        select(PlaygroundMessage)
        .where(PlaygroundMessage.session_id == session.id)
        .order_by(PlaygroundMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [PlaygroundMessageOut.model_validate(r) for r in rows]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session_endpoint(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    session = await _fetch_session_or_404(db, session_id, user)
    await db.delete(session)
    await db.commit()


# ===========================================================================
# 채팅 (SSE)
# ===========================================================================


@router.post("/chat")
async def chat_endpoint(
    body: PlaygroundChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    # 세션 확보 (없으면 생성).
    if body.session_id is None:
        session = await create_session(
            db,
            user_id=user.id,
            provider=body.provider,
            model=body.model,
            system_prompt=body.system_prompt,
            temperature=body.temperature,
        )
    else:
        session = await _fetch_session_or_404(db, body.session_id, user)

    await append_message(
        db,
        session_id=session.id,
        role="user",
        content=body.message,
    )

    stmt = (
        select(PlaygroundMessage)
        .where(PlaygroundMessage.session_id == session.id)
        .order_by(PlaygroundMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    history = result.scalars().all()
    api_messages = [
        {"role": m.role, "content": m.content}
        for m in history
        if m.role in ("user", "assistant")
    ]

    raw_request = mask_request_payload(
        {
            "model": body.model,
            "temperature": body.temperature,
            "system_prompt": body.system_prompt,
            "message_count": len(api_messages),
            "headers": {"Authorization": "***masked***"},
        }
    )
    assistant_msg = await append_message(
        db,
        session_id=session.id,
        role="assistant",
        content="",
        model=body.model,
        raw_request=raw_request,
    )

    async def event_gen():
        buffer: list[str] = []
        usage: dict[str, int] = {}
        start = time.perf_counter()
        try:
            async for chunk in stream_chat(
                messages=api_messages,
                model=body.model,
                system_prompt=session.system_prompt or body.system_prompt,
                temperature=float(session.temperature)
                if session.temperature is not None
                else body.temperature,
            ):
                if chunk["type"] == "text_delta":
                    buffer.append(chunk["delta"])
                elif chunk["type"] == "usage":
                    usage = {k: v for k, v in chunk.items() if k != "type"}
                elif chunk["type"] == "error":
                    logger.warning("playground stream error: %s", chunk.get("message"))
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        finally:
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            full_text = "".join(buffer)
            input_tok = usage.get("input_tokens")
            output_tok = usage.get("output_tokens")
            cache_read = usage.get("cache_read_input_tokens", 0) or 0
            cache_create = usage.get("cache_creation_input_tokens", 0) or 0
            cached_total = cache_read + cache_create if usage else None
            cost = calc_text_cost(
                model=body.model,
                input_tokens=input_tok,
                output_tokens=output_tok,
                cached_tokens=cached_total,
            )
            await update_metrics(
                db,
                message_id=assistant_msg.id,
                content=full_text,
                input_tokens=input_tok,
                output_tokens=output_tok,
                cached_tokens=cached_total,
                latency_ms=elapsed_ms,
                raw_response=usage or None,
                cost_usd=cost,
            )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ===========================================================================
# 이미지/영상 — DB 영속화 포함
# ===========================================================================


@router.post("/image", response_model=PlaygroundTaskCreated)
async def create_image_task_endpoint(
    body: PlaygroundImageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundTaskCreated:
    try:
        name, version = parse_model_key(body.model_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        resp = await create_image_task(
            prompt=body.prompt,
            model_name=name,
            model_version=version,
            negative_prompt=body.negative_prompt,
            aspect_ratio=body.aspect_ratio,
            enhance_prompt=body.enhance_prompt,
        )
    except RuntimeError as exc:
        logger.warning("create_image_task 실패: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    task_id = resp.get("TaskId")
    if not task_id:
        raise HTTPException(status_code=502, detail=f"텐센트 응답에 TaskId 없음: {resp}")

    media = PlaygroundMedia(
        user_id=user.id,
        media_type="image",
        task_id=str(task_id),
        model_key=body.model_key,
        prompt=body.prompt,
        status="running",
    )
    db.add(media)
    await db.commit()

    return PlaygroundTaskCreated(task_id=str(task_id), request_id=resp.get("RequestId"), kind="image")


@router.post("/video", response_model=PlaygroundTaskCreated)
async def create_video_task_endpoint(
    body: PlaygroundVideoRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundTaskCreated:
    try:
        name, version = parse_model_key(body.model_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        resp = await create_video_task(
            prompt=body.prompt,
            model_name=name,
            model_version=version,
            duration=body.duration,
            resolution=body.resolution,
            aspect_ratio=body.aspect_ratio,
            audio_generation=body.audio_generation,
            enhance_prompt=body.enhance_prompt,
        )
    except RuntimeError as exc:
        logger.warning("create_video_task 실패: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    task_id = resp.get("TaskId")
    if not task_id:
        raise HTTPException(status_code=502, detail=f"텐센트 응답에 TaskId 없음: {resp}")

    media = PlaygroundMedia(
        user_id=user.id,
        media_type="video",
        task_id=str(task_id),
        model_key=body.model_key,
        prompt=body.prompt,
        status="running",
        duration_sec=Decimal(body.duration),
    )
    db.add(media)
    await db.commit()

    return PlaygroundTaskCreated(task_id=str(task_id), request_id=resp.get("RequestId"), kind="video")


@router.get("/tasks/{kind}/{task_id}", response_model=PlaygroundTaskStatus)
async def describe_task_endpoint(
    kind: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundTaskStatus:
    if kind not in ("image", "video"):
        raise HTTPException(status_code=400, detail="kind 는 image 또는 video")

    try:
        resp = await describe_image_task(task_id)
    except RuntimeError as exc:
        logger.warning("describe %s task 실패: %s", kind, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    raw_status = str(resp.get("Status") or "").upper()
    if raw_status == "FINISH":
        status_norm = "succeeded"
    elif raw_status == "FAIL":
        status_norm = "failed"
    elif raw_status == "PROCESSING":
        status_norm = "running"
    elif raw_status in {"PENDING", "WAITING", "QUEUED"}:
        status_norm = "pending"
    else:
        status_norm = "unknown"

    inner_key = "AigcImageTask" if kind == "image" else "AigcVideoTask"
    inner = resp.get(inner_key) or {}
    output_url: str | None = None
    error_message: str | None = None
    width: int | None = None
    height: int | None = None
    if isinstance(inner, dict):
        file_infos = (inner.get("Output") or {}).get("FileInfos") or []
        if file_infos:
            first = file_infos[0]
            output_url = first.get("FileUrl")
            meta = first.get("MetaData") or {}
            if isinstance(meta, dict):
                w = meta.get("Width")
                h = meta.get("Height")
                if isinstance(w, int):
                    width = w
                if isinstance(h, int):
                    height = h
        err_code = inner.get("ErrCode")
        msg = inner.get("Message")
        if err_code and err_code != 0:
            status_norm = "failed"
            error_message = msg or f"ErrCode={err_code}"

    # DB 동기화 — 본인 task 만 다룬다 (다른 사용자의 task_id 라도 텐센트는 응답하지만, 우리는 본인 row만 update).
    media_stmt = select(PlaygroundMedia).where(
        PlaygroundMedia.task_id == task_id,
        PlaygroundMedia.user_id == user.id,
    )
    media_row = (await db.execute(media_stmt)).scalar_one_or_none()
    if media_row is not None:
        media_row.status = status_norm
        media_row.error_message = error_message
        media_row.url = output_url
        if width:
            media_row.width = width
        if height:
            media_row.height = height
        # 백엔드 디스크 다운로드 + 만료/비용 채우기 (한 번만).
        if status_norm == "succeeded" and output_url and not media_row.file_path:
            file_path = await download_media(
                url=output_url,
                user_id=user.id,
                task_id=task_id,
                kind=kind,
            )
            if file_path:
                media_row.file_path = file_path
            media_row.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
            # 비용 계산
            if kind == "image":
                media_row.cost_usd = calc_image_cost(media_row.model_key)
            else:
                dur = int(media_row.duration_sec) if media_row.duration_sec else 0
                media_row.cost_usd = calc_video_cost(media_row.model_key, dur)
        await db.commit()

    return PlaygroundTaskStatus(
        task_id=task_id,
        kind=kind,
        status=status_norm,
        output_url=output_url,
        error_message=error_message,
        raw=resp,
    )


# ===========================================================================
# 미디어 목록 + 파일 서빙
# ===========================================================================


@router.get("/media", response_model=list[PlaygroundMediaOut])
async def list_my_media(
    kind: Literal["image", "video"] | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[PlaygroundMediaOut]:
    """본인이 만든 미디어 목록 (최신순). kind 로 필터."""
    stmt = (
        select(PlaygroundMedia)
        .where(PlaygroundMedia.user_id == user.id)
        .order_by(desc(PlaygroundMedia.created_at))
        .limit(limit)
    )
    if kind:
        stmt = stmt.where(PlaygroundMedia.media_type == kind)
    rows = (await db.execute(stmt)).scalars().all()
    return [PlaygroundMediaOut.model_validate(r) for r in rows]


@router.get("/media/{media_id}/file")
async def serve_media_file(
    media_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> FileResponse:
    """본인 미디어 파일 서빙. file_path 가 있으면 디스크에서 직접 (영구 보관)."""
    row = (
        await db.execute(
            select(PlaygroundMedia).where(PlaygroundMedia.id == media_id)
        )
    ).scalar_one_or_none()
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="미디어를 찾을 수 없습니다")
    if not row.file_path or not os.path.exists(row.file_path):
        raise HTTPException(status_code=404, detail="파일이 아직 준비되지 않았습니다")
    media_root = os.path.abspath(settings.playground_media_root)
    real_path = os.path.abspath(row.file_path)
    # path traversal 차단
    if not real_path.startswith(media_root + os.sep):
        raise HTTPException(status_code=403, detail="허용되지 않은 경로")
    return FileResponse(real_path)


# ===========================================================================
# 관리자: 사용량 대시보드
# ===========================================================================


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


# ===========================================================================
# helpers
# ===========================================================================


async def _fetch_session_or_404(
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
