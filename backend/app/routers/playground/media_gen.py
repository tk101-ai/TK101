"""이미지/영상 생성 task — 생성/i2v/폴링. DB 영속화 포함."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
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


def compute_media_expires_at(
    storage_mode: str, kind: str, now: datetime
) -> datetime | None:
    """재편집(i2i/i2v/v2v) 베이스 URL 의 만료 시각을 저장 모드로 결정한다.

    - ``Permanent`` (기본, #161): 만료 없음 → ``None``. 재편집 가드가 막지 않는다.
    - ``Temporary``: 텐센트 실제 만료 반영 — 이미지 ~7d / 영상 ~24h.

    디스크 정리는 ``expires_at`` 이 아니라 ``created_at`` 기준이라 무관
    (media_cleanup 참고). 이 값은 오직 재편집 가드에서만 쓰인다.
    """
    if storage_mode.strip().lower() == "permanent":
        return None
    ttl = timedelta(days=7) if kind == "image" else timedelta(hours=24)
    return now + ttl


async def assert_source_fetchable(url: str, label: str) -> None:
    """텐센트가 리터치 베이스(원본)를 실제로 가져갈 수 있는지 사전 확인.

    베이스 URL 은 텐센트 COS 서명 URL 이라 물리적으로 만료(~24h)된다. DB 의
    ``expires_at`` 은 #161(StorageMode=Permanent) 이후 None 이라 재편집 가드가
    이걸 못 잡고, 만료된 URL 을 텐센트에 넘기면 텐센트는 원본을 못 받아 사실상
    t2v(프롬프트만)로 엉뚱한 결과를 조용히 뱉는다(운영 확인: 토끼 영상 → 남자/건물).
    무의미한 유료 생성을 막기 위해 실제로 GET(Range)으로 접근성을 확인한다.

    COS presigned URL 은 method 별 서명이라 HEAD 는 오탐(403)이 나므로 GET+Range 를
    쓴다. 네트워크 일시 오류는 차단하지 않고 텐센트가 시도하도록 통과시킨다.
    """
    try:
        async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
            resp = await client.get(url, headers={"Range": "bytes=0-0"})
    except httpx.HTTPError:
        return  # 일시 네트워크 오류 — 차단하지 않음
    if resp.status_code in (401, 403, 404, 410):
        raise HTTPException(
            status_code=400,
            detail=(
                f"베이스 {label}의 원본 URL 이 만료되어 리터치할 수 없습니다. "
                f"원본 {label}을(를) 다시 생성한 뒤(최신 생성분) 리터치해 주세요."
            ),
        )


def tencent_runtime_to_http(exc: RuntimeError) -> HTTPException:
    """텐센트 RuntimeError 를 사용자 친화 HTTPException 으로 변환.

    동시성 한도(RequestLimitExceeded)는 일시적이라 429 로 안내하고, 그 외는 503.
    """
    low = str(exc).lower()
    if "requestlimitexceeded" in low or "concurrency" in low:
        return HTTPException(
            status_code=429,
            detail=(
                "현재 텐센트 영상 생성 동시 처리 한도에 도달했습니다. "
                "진행 중인 생성이 끝난 뒤 잠시 후 다시 시도해 주세요."
            ),
        )
    return HTTPException(status_code=503, detail=str(exc))


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
        raise tencent_runtime_to_http(exc) from exc

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
        raise tencent_runtime_to_http(exc) from exc

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
    # 텐센트가 가져갈 수 있는 URL 필요. StorageMode=Permanent(기본, #161)면 만료
    # 없이 재편집 가능(expires_at 미설정). Temporary 면 텐센트 실제 만료(영상 ~24h /
    # 이미지 ~7d) 를 반영해 expires_at 이 지난 경우만 차단한다.
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
    # StorageMode=Permanent 면 expires_at 이 None 이라 위 가드가 안 걸리지만, 텐센트
    # 서명 URL 은 물리적으로 만료되므로 실제 접근성을 확인해 무의미한 생성을 막는다.
    await assert_source_fetchable(source_url, label)

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
            # v2v: 베이스 영상의 원본 프롬프트를 넘겨, 사용자가 피사체를 언급하지
            # 않아도 원본 주체가 유지되도록 프롬프트 앵커로 사용한다.
            source_prompt=source_row.prompt if is_video_source else None,
        )
    except RuntimeError as exc:
        logger.warning("create_video_task (%s) 실패: %s", "v2v" if is_video_source else "i2v", exc)
        raise tencent_runtime_to_http(exc) from exc

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
    # 서명 URL 물리적 만료 사전 확인 (v2v 와 동일 이유).
    await assert_source_fetchable(image_url, "이미지")

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
        raise tencent_runtime_to_http(exc) from exc

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
            media_row.expires_at = compute_media_expires_at(
                settings.tencent_aigc_storage_mode, kind, datetime.now(timezone.utc)
            )
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
