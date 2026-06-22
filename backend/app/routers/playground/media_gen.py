"""이미지/영상 생성 task — 생성/i2v/폴링. DB 영속화 포함."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.playground import PlaygroundMedia
from app.models.user import User
from app.schemas.playground import (
    PlaygroundI2VRequest,
    PlaygroundImageRequest,
    PlaygroundTaskCreated,
    PlaygroundTaskStatus,
    PlaygroundVideoRequest,
)
from app.services.playground.media_downloader import download_media
from app.services.playground.pricing import calc_image_cost, calc_video_cost
from app.services.playground.tencent_aigc_media import (
    create_image_task,
    create_video_task,
    describe_image_task,
    parse_model_key,
)
from app.services.playground.usage_check import check_quota_or_raise

from ._common import ensure_attachment_is_user_image, make_subrouter

logger = logging.getLogger(__name__)

router: APIRouter = make_subrouter()


@router.post("/image", response_model=PlaygroundTaskCreated)
async def create_image_task_endpoint(
    body: PlaygroundImageRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundTaskCreated:
    await check_quota_or_raise(db, user)
    # 베이스 이미지 — 텐센트 reference-image spec 확인 전이라 가드.
    if body.reference_attachment_id is not None:
        await ensure_attachment_is_user_image(db, body.reference_attachment_id, user)
        raise HTTPException(
            status_code=503,
            detail=(
                "베이스 이미지 기반 생성은 텐센트 reference-image API spec 확인 후 활성화됩니다. "
                "현재는 베이스 없이 프롬프트만으로 생성하세요"
            ),
        )

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
    await check_quota_or_raise(db, user)
    # 베이스 이미지 — 텐센트 reference-image spec 확인 전이라 가드 (i2v 와 동일).
    if body.reference_attachment_id is not None:
        await ensure_attachment_is_user_image(db, body.reference_attachment_id, user)
        raise HTTPException(
            status_code=503,
            detail=(
                "베이스 이미지 기반 영상 생성은 텐센트 reference-image API spec 확인 후 활성화됩니다. "
                "현재는 베이스 없이 프롬프트만으로 생성하세요"
            ),
        )
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


@router.post("/video/from-media", response_model=PlaygroundTaskCreated)
async def create_video_from_media_endpoint(
    body: PlaygroundI2VRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundTaskCreated:
    """Image-to-Video (i2v).

    image_media_id 로 본인의 완료된 이미지 PlaygroundMedia 를 참조해서
    텐센트 영상 task 생성. ``Input.FileInfos[0].FileUrl`` 필드명은 추정치 —
    라이브 probe 후 필요 시 ``tencent_aigc_media.create_video_task`` 의 매핑 수정.
    """
    await check_quota_or_raise(db, user)

    # 참조 이미지 row 조회 (본인 + 성공한 image task 만).
    stmt = select(PlaygroundMedia).where(
        PlaygroundMedia.id == body.image_media_id,
        PlaygroundMedia.user_id == user.id,
        PlaygroundMedia.media_type == "image",
        PlaygroundMedia.status == "succeeded",
    )
    image_row = (await db.execute(stmt)).scalar_one_or_none()
    if image_row is None:
        raise HTTPException(
            status_code=404, detail="참조 이미지 미디어를 찾을 수 없습니다",
        )
    # 텐센트 임시 URL 이 있고 만료 안 됐으면 그걸 우선 사용. 아니면 거부 (백엔드
    # 파일 → 텐센트 노출 URL 만들기는 별도 작업 필요).
    image_url = image_row.url
    if not image_url:
        raise HTTPException(
            status_code=400,
            detail="참조 이미지의 텐센트 URL 이 없습니다 (만료되었거나 미보관)",
        )
    if image_row.expires_at and image_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400, detail="참조 이미지 URL 이 만료되었습니다",
        )

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
            input_image_url=image_url,
        )
    except RuntimeError as exc:
        logger.warning("create_video_task (i2v) 실패: %s", exc)
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

    return PlaygroundTaskCreated(
        task_id=str(task_id), request_id=resp.get("RequestId"), kind="video",
    )


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
                department=user.department,
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
        media_id=media_row.id if media_row is not None else None,
    )
