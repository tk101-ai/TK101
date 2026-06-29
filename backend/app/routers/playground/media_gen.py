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
    PlaygroundImageEditRequest,
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
    describe_aigc_image_task,
    describe_aigc_video_task,
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
    """Image-to-Video (i2v) 또는 Video-to-Video (v2v, 영상 리터치).

    image_media_id 로 본인의 완료된 미디어(이미지 또는 영상)를 베이스로 영상 task
    생성. 소스가 이미지면 i2v(ImageUrl), 영상이면 v2v(VideoInfos). 결과 조회는
    DescribeAigcVideoTask 공통.
    """
    await check_quota_or_raise(db, user)

    # 베이스 미디어 row 조회 (본인 + 성공한 이미지/영상). 영상이면 v2v.
    stmt = select(PlaygroundMedia).where(
        PlaygroundMedia.id == body.image_media_id,
        PlaygroundMedia.user_id == user.id,
        PlaygroundMedia.media_type.in_(("image", "video")),
        PlaygroundMedia.status == "succeeded",
    )
    source_row = (await db.execute(stmt)).scalar_one_or_none()
    if source_row is None:
        raise HTTPException(
            status_code=404, detail="베이스 미디어를 찾을 수 없습니다",
        )
    is_video_source = source_row.media_type == "video"
    label = "영상" if is_video_source else "이미지"
    # 텐센트가 가져갈 수 있는 URL 필요. 생성 영상의 COS 서명 URL 은 ~12h 만료라
    # 최근 생성분만 v2v 가능(만료 시 명확한 에러).
    source_url = source_row.url
    if not source_url:
        raise HTTPException(
            status_code=400,
            detail=f"베이스 {label}의 텐센트 URL 이 없습니다 (만료되었거나 미보관)",
        )
    if source_row.expires_at and source_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400, detail=f"베이스 {label} URL 이 만료되었습니다",
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
            input_video_url=source_url if is_video_source else None,
            input_image_url=None if is_video_source else source_url,
        )
    except RuntimeError as exc:
        logger.warning("create_video_task (%s) 실패: %s", "v2v" if is_video_source else "i2v", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    task_id = resp.get("TaskId")
    if not task_id:
        raise HTTPException(status_code=502, detail=f"텐센트 응답에 TaskId 없음: {resp}")

    media = PlaygroundMedia(
        user_id=user.id,
        media_type="video",
        source_media_id=source_row.id,  # 어떤 미디어(이미지/영상)로 만든 영상인지
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


@router.post("/image/from-media", response_model=PlaygroundTaskCreated)
async def create_image_from_media_endpoint(
    body: PlaygroundImageEditRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> PlaygroundTaskCreated:
    """Image-to-Image (i2i) — 완성 이미지를 베이스로 리터치/편집.

    image_media_id 로 본인의 완료된 이미지를 참조해 MPS CreateAigcImageTask
    (ImageInfos) 로 편집 이미지 생성. 결과는 DescribeAigcImageTask 로 조회.
    """
    await check_quota_or_raise(db, user)

    stmt = select(PlaygroundMedia).where(
        PlaygroundMedia.id == body.image_media_id,
        PlaygroundMedia.user_id == user.id,
        PlaygroundMedia.media_type == "image",
        PlaygroundMedia.status == "succeeded",
    )
    image_row = (await db.execute(stmt)).scalar_one_or_none()
    if image_row is None:
        raise HTTPException(
            status_code=404, detail="참조 이미지 미디어를 찾을 수 없습니다"
        )
    image_url = image_row.url
    if not image_url:
        raise HTTPException(
            status_code=400,
            detail="참조 이미지의 텐센트 URL 이 없습니다 (만료되었거나 미보관)",
        )
    if image_row.expires_at and image_row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400, detail="참조 이미지 URL 이 만료되었습니다"
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
            aspect_ratio=body.aspect_ratio,
            enhance_prompt=body.enhance_prompt,
            input_image_url=image_url,
        )
    except RuntimeError as exc:
        logger.warning("create_image_task (i2i) 실패: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    task_id = resp.get("TaskId")
    if not task_id:
        raise HTTPException(status_code=502, detail=f"텐센트 응답에 TaskId 없음: {resp}")

    media = PlaygroundMedia(
        user_id=user.id,
        media_type="image",
        source_media_id=image_row.id,  # 어떤 이미지를 리터치했는지
        task_id=str(task_id),
        model_key=body.model_key,
        prompt=body.prompt,
        status="running",
    )
    db.add(media)
    await db.commit()

    return PlaygroundTaskCreated(
        task_id=str(task_id), request_id=resp.get("RequestId"), kind="image",
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

    output_url: str | None = None
    error_message: str | None = None
    width: int | None = None
    height: int | None = None

    # i2v(image-to-video)는 MPS CreateAigcVideoTask 로 생성(task_id 에 "AigcVideo-",
    # VOD 의 t2v 는 "AigcVideoTask-"). MPS AIGC 영상 결과는 전용 액션
    # DescribeAigcVideoTask 로 조회한다(일반 DescribeTaskDetail 은 ResourceNotFound).
    is_mps_video = (
        kind == "video"
        and "AigcVideo-" in task_id
        and "AigcVideoTask" not in task_id
    )
    # i2i(image-to-image, 리터치)는 MPS CreateAigcImageTask("AigcImage-", VOD t2i 는
    # "AigcImageTask-"). 결과는 전용 액션 DescribeAigcImageTask 로 조회.
    is_mps_image = (
        kind == "image"
        and "AigcImage-" in task_id
        and "AigcImageTask" not in task_id
    )

    if is_mps_image:
        try:
            resp = await describe_aigc_image_task(task_id)
        except RuntimeError as exc:
            logger.warning("describe MPS i2i 실패: %s", exc)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        # {Status: RUN|DONE|FAIL.., ImageUrls: [signed_url], Message}
        raw_status = str(resp.get("Status") or "").upper()
        if raw_status == "DONE":
            status_norm = "succeeded"
        elif raw_status in {"FAIL", "FAILED", "ERROR"}:
            status_norm = "failed"
        elif raw_status in {"RUN", "RUNNING", "PROCESSING"}:
            status_norm = "running"
        elif raw_status in {"WAIT", "WAITING", "PENDING", "QUEUED"}:
            status_norm = "pending"
        else:
            status_norm = "unknown"
        urls = resp.get("ImageUrls") or []
        if isinstance(urls, list) and urls:
            output_url = urls[0]
        if status_norm == "failed":
            error_message = str(resp.get("Message") or "이미지 리터치 실패")
    elif is_mps_video:
        try:
            resp = await describe_aigc_video_task(task_id)
        except RuntimeError as exc:
            logger.warning("describe MPS i2v 실패: %s", exc)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        # {Status: RUN|DONE|FAIL.., VideoUrls: [signed_url], Resolution: "WxH", Message}
        raw_status = str(resp.get("Status") or "").upper()
        if raw_status == "DONE":
            status_norm = "succeeded"
        elif raw_status in {"FAIL", "FAILED", "ERROR"}:
            status_norm = "failed"
        elif raw_status in {"RUN", "RUNNING", "PROCESSING"}:
            status_norm = "running"
        elif raw_status in {"WAIT", "WAITING", "PENDING", "QUEUED"}:
            status_norm = "pending"
        else:
            status_norm = "unknown"
        urls = resp.get("VideoUrls") or []
        if isinstance(urls, list) and urls:
            output_url = urls[0]
        res = str(resp.get("Resolution") or "")
        if "x" in res.lower():
            try:
                w_s, h_s = res.lower().split("x")[:2]
                width, height = int(w_s), int(h_s)
            except ValueError:
                pass
        if status_norm == "failed":
            error_message = str(resp.get("Message") or "i2v 생성 실패")
    else:
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
