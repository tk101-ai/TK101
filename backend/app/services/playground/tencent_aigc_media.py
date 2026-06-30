"""Tencent AIGC Image/Video task 클라이언트 (T8 Phase 4/5).

라이브 probe (2026-05-19) 로 확정된 호출 구조:

이미지 생성 (Create):
    POST https://vod.intl.tencentcloudapi.com/
    service=vod  version=2018-07-17  action=CreateAigcImageTask
    body = {SubAppId, ModelName, ModelVersion, Prompt, NegativePrompt?, EnhancePrompt?, OutputConfig}
    response = {Response: {TaskId, RequestId}}

영상 생성 (Create):
    POST https://vod.intl.tencentcloudapi.com/
    action=CreateAigcVideoTask
    body = {SubAppId, ModelName, ModelVersion, Prompt, EnhancePrompt?, OutputConfig{Duration, Resolution, ...}}

폴링 (Describe):
    같은 endpoint, **action=DescribeTaskDetail** (Image/Video 통합 — DescribeAigc*Task 는 vod 에 없음)
    body = {SubAppId, TaskId}
    response 핵심 필드:
        Status             — "PROCESSING" | "FINISH" | "FAIL"
        TaskType           — "AigcImageTask" | "AigcVideoTask"
        AigcImageTask      — { Status, Progress, ErrCode, Message, Input, Output{FileInfos[]} }
        AigcVideoTask      — 같은 구조 (Output.FileInfos[0].FileUrl)
        Output.FileInfos[0].FileUrl  — 7일 임시 스토리지 URL

서명: token_manager 의 ``_build_signed_headers`` 재사용 (텐센트 v3 표준).
설정: TENCENT_AIGC_{SECRET_ID,SECRET_KEY,SUBAPP_ID} env 필수.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import settings
from app.services.playground.token_manager import _build_signed_headers

logger = logging.getLogger(__name__)


_SERVICE = "vod"
_VERSION = "2018-07-17"


# ---------------------------------------------------------------------------
# 공통: VOD intl endpoint 에 TC3 서명 POST
# ---------------------------------------------------------------------------
async def _call_vod_intl(action: str, payload_obj: dict[str, Any]) -> dict[str, Any]:
    """vod.intl.tencentcloudapi.com 에 TC3-HMAC-SHA256 서명된 POST 호출.

    Returns:
        텐센트 표준 응답의 ``Response`` 객체 (envelope 벗겨낸 채로).

    Raises:
        RuntimeError: 시크릿 미설정 / 텐센트 Error envelope / 네트워크 실패.
    """
    if not settings.tencent_aigc_secret_id or not settings.tencent_aigc_secret_key:
        raise RuntimeError("텐센트 SecretId/Key 미설정")
    if not settings.tencent_aigc_subapp_id:
        raise RuntimeError("텐센트 SubAppId 미설정")

    host = settings.tencent_aigc_vod_intl_endpoint
    url = f"https://{host}"
    # ensure_ascii=True 로 명시: TC3 서명은 payload 의 byte 단위 SHA256 을 사용하므로
    # 클라이언트와 서버 양쪽이 같은 byte 시퀀스를 봐야 함. 비ASCII 가 prompt 에 들어가도 안전.
    payload = json.dumps(payload_obj, separators=(",", ":"), ensure_ascii=True)
    timestamp = int(datetime.now(timezone.utc).timestamp())

    headers = _build_signed_headers(
        secret_id=settings.tencent_aigc_secret_id,
        secret_key=settings.tencent_aigc_secret_key,
        service=_SERVICE,
        host=host,
        action=action,
        version=_VERSION,
        region=settings.tencent_aigc_region,
        payload=payload,
        timestamp=timestamp,
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, headers=headers, content=payload)
        resp.raise_for_status()
        data = resp.json()

    response = data.get("Response", {})
    if "Error" in response:
        err = response["Error"]
        raise RuntimeError(
            f"텐센트 {action} 오류: {err.get('Code')} - {err.get('Message')}"
        )
    return response


async def _call_mps_intl(action: str, payload_obj: dict[str, Any]) -> dict[str, Any]:
    """mps.intl.tencentcloudapi.com (Media Processing Service) TC3 서명 POST.

    i2v(CreateAigcVideoTask)는 공개문서상 MPS 소속이라 VOD와 별도 호출.
    서명은 동일한 TC3 helper, service=mps / version=2019-06-12 로만 다르다.
    """
    if not settings.tencent_aigc_secret_id or not settings.tencent_aigc_secret_key:
        raise RuntimeError("텐센트 SecretId/Key 미설정")

    host = settings.tencent_aigc_mps_intl_endpoint
    url = f"https://{host}"
    payload = json.dumps(payload_obj, separators=(",", ":"), ensure_ascii=True)
    timestamp = int(datetime.now(timezone.utc).timestamp())

    headers = _build_signed_headers(
        secret_id=settings.tencent_aigc_secret_id,
        secret_key=settings.tencent_aigc_secret_key,
        service="mps",
        host=host,
        action=action,
        version=settings.tencent_aigc_mps_version,
        region=settings.tencent_aigc_region,
        payload=payload,
        timestamp=timestamp,
    )

    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(url, headers=headers, content=payload)
        resp.raise_for_status()
        data = resp.json()

    response = data.get("Response", {})
    if "Error" in response:
        err = response["Error"]
        raise RuntimeError(
            f"텐센트(MPS) {action} 오류: {err.get('Code')} - {err.get('Message')}"
        )
    return response


# ---------------------------------------------------------------------------
# Image: CreateAigcImageTask
# ---------------------------------------------------------------------------
async def create_image_task(
    *,
    prompt: str,
    model_name: str = "Kling",
    model_version: str = "2.1",
    negative_prompt: str | None = None,
    aspect_ratio: str = "1:1",
    enhance_prompt: bool = True,
    input_image_url: str | None = None,
) -> dict[str, Any]:
    """Create image generation task. Returns {TaskId, RequestId}.

    ``input_image_url`` 가 주어지면 image-to-image(i2i, 리터치/편집) 모드 —
    MPS CreateAigcImageTask 에 ``ImageInfos[{ImageUrl}]`` 로 베이스 이미지를 전달
    (i2v 와 동일 계열, 결과는 DescribeAigcImageTask 로 조회). 없으면 VOD t2i.
    """
    if input_image_url:
        mps_body: dict[str, Any] = {
            "ModelName": model_name,
            "ModelVersion": model_version,
            "Prompt": prompt,
            # 참고/베이스 이미지(편집 대상). AigcImageInfo 배열, 1장 기본.
            "ImageInfos": [{"ImageUrl": input_image_url}],
        }
        if settings.tencent_aigc_mps_cos_bucket and settings.tencent_aigc_mps_cos_region:
            mps_body["StoreCosParam"] = {
                "CosBucketName": settings.tencent_aigc_mps_cos_bucket,
                "CosBucketRegion": settings.tencent_aigc_mps_cos_region,
                "CosBucketPath": settings.tencent_aigc_mps_cos_path,
            }
        return await _call_mps_intl("CreateAigcImageTask", mps_body)

    output_config: dict[str, Any] = {
        "StorageMode": settings.tencent_aigc_storage_mode,
        "AspectRatio": aspect_ratio,
        "InputComplianceCheck": "Enabled",
        "OutputComplianceCheck": "Enabled",
    }
    body: dict[str, Any] = {
        "SubAppId": int(settings.tencent_aigc_subapp_id),
        "ModelName": model_name,
        "ModelVersion": model_version,
        "Prompt": prompt,
        "EnhancePrompt": "Enabled" if enhance_prompt else "Disabled",
        "OutputConfig": output_config,
    }
    if negative_prompt:
        body["NegativePrompt"] = negative_prompt

    return await _call_vod_intl("CreateAigcImageTask", body)


async def describe_aigc_image_task(task_id: str) -> dict[str, Any]:
    """MPS i2i 결과 조회 — AIGC 전용 액션. {Status, ImageUrls, Message}.

    DescribeAigcVideoTask 의 이미지 버전(일반 DescribeTaskDetail 은 ResourceNotFound).
    """
    return await _call_mps_intl("DescribeAigcImageTask", {"TaskId": task_id})


async def describe_task_detail(task_id: str) -> dict[str, Any]:
    """Image/Video 통합 폴링 (vod DescribeTaskDetail).

    응답 핵심:
        Status = "PROCESSING" | "FINISH" | "FAIL"
        TaskType = "AigcImageTask" | "AigcVideoTask"
        AigcImageTask = { Status, Progress, ErrCode, Message, Output{FileInfos[]} }
        AigcVideoTask = 같은 구조
    """
    body = {
        "SubAppId": int(settings.tencent_aigc_subapp_id),
        "TaskId": task_id,
    }
    return await _call_vod_intl("DescribeTaskDetail", body)


# 하위 호환 alias — 라우터/외부 코드가 describe_image_task/describe_video_task 를 import 해도 동작.
describe_image_task = describe_task_detail
describe_video_task = describe_task_detail


# ---------------------------------------------------------------------------
# Video: CreateAigcVideoTask
# ---------------------------------------------------------------------------
# v2v(영상 리터치) 충실도 보강: 텐센트 VideoInfos 기반 v2v 는 레퍼런스 "재생성"이라
# 사용자 프롬프트가 우세하면 원본의 화풍/구성이 약하게만 반영된다(운영 확인:
# 애니 토끼 → 흰토끼 요청 → 실사 흰토끼). 사용자 프롬프트 앞에 원본 스타일·구성을
# 유지하라는 지시를 자동 prepend 해 충실도를 끌어올린다(베스트에포트 — 벤더 한계상
# 완전 보장은 아님). 한/영 병기로 EnhancePrompt 재작성에도 의도가 남게 한다.
_V2V_STYLE_PRESERVE_PREFIX = (
    "원본 영상의 비주얼 스타일·화풍·색감·구도·구성을 최대한 유지하고, "
    "아래 요청 사항만 반영해 편집하세요. "
    "Preserve the original video's visual style, art direction, color, and composition; "
    "apply only the following change: "
)


async def create_video_task(
    *,
    prompt: str,
    model_name: str = "Kling",
    model_version: str = "3.0-Omni",
    duration: int = 5,
    resolution: str = "720P",
    aspect_ratio: str = "16:9",
    audio_generation: bool = False,
    enhance_prompt: bool = True,
    input_image_url: str | None = None,
    input_video_url: str | None = None,
) -> dict[str, Any]:
    """Create video generation task. Returns {TaskId, RequestId}.

    MPS CreateAigcVideoTask 입력 분기(라이브 probe 확정):
    - ``input_video_url`` → v2v(영상 리터치): ``VideoInfos:[{VideoUrl}]``.
    - ``input_image_url`` → i2v(이미지→영상): top-level ``ImageUrl``.
    - 둘 다 없으면 VOD t2v(임시저장).
    결과 조회는 전용 액션 ``DescribeAigcVideoTask``.
    """
    body: dict[str, Any] = {
        "SubAppId": int(settings.tencent_aigc_subapp_id),
        "ModelName": model_name,
        "ModelVersion": model_version,
        "Prompt": prompt,
        "EnhancePrompt": "Enabled" if enhance_prompt else "Disabled",
        "OutputConfig": {
            "StorageMode": settings.tencent_aigc_storage_mode,
            "Duration": duration,
            "Resolution": resolution,
            "AspectRatio": aspect_ratio,
            "AudioGeneration": "Enabled" if audio_generation else "Disabled",
            "InputComplianceCheck": "Enabled",
            "OutputComplianceCheck": "Enabled",
        },
    }
    if input_video_url or input_image_url:
        # MPS CreateAigcVideoTask (공개문서 1041/76487). 출력은 MPS 기본 COS 버킷에
        # 저장(StoreCosParam 미지정 시 계정 기본). 결과 조회는 DescribeAigcVideoTask.
        mps_body: dict[str, Any] = {
            "ModelName": model_name,
            "ModelVersion": model_version,
            "Prompt": prompt,
            "Duration": duration,
            "ExtraParameters": {
                "Resolution": resolution,
                "AspectRatio": aspect_ratio,
            },
        }
        if input_video_url:
            # v2v(video-to-video, 영상 리터치): 베이스 영상은 VideoInfos 배열.
            mps_body["VideoInfos"] = [{"VideoUrl": input_video_url}]
            # 원본 스타일 유지 지시를 프롬프트 앞에 붙여 재생성 충실도 보강.
            mps_body["Prompt"] = _V2V_STYLE_PRESERVE_PREFIX + prompt
        else:
            # i2v(image-to-video): 베이스 이미지는 top-level ImageUrl.
            mps_body["ImageUrl"] = input_image_url
        # 출력 버킷을 명시 설정한 경우에만 지정(미설정이면 MPS 기본 버킷 사용).
        if settings.tencent_aigc_mps_cos_bucket and settings.tencent_aigc_mps_cos_region:
            mps_body["StoreCosParam"] = {
                "CosBucketName": settings.tencent_aigc_mps_cos_bucket,
                "CosBucketRegion": settings.tencent_aigc_mps_cos_region,
                "CosBucketPath": settings.tencent_aigc_mps_cos_path,
            }
        return await _call_mps_intl("CreateAigcVideoTask", mps_body)
    return await _call_vod_intl("CreateAigcVideoTask", body)


async def describe_aigc_video_task(task_id: str) -> dict[str, Any]:
    """MPS i2v 결과 조회 — AIGC 전용 액션. {Status, VideoUrls, Resolution, Message}.

    일반 ``DescribeTaskDetail`` 은 AIGC task 를 ResourceNotFound 로 못 찾는다 —
    AIGC 는 Describe**Aigc**VideoTask 가 정식 조회 액션(문서 mps.live/33644).
    """
    return await _call_mps_intl("DescribeAigcVideoTask", {"TaskId": task_id})


# ---------------------------------------------------------------------------
# 모델 카탈로그 — 2026-05-19 라이브 probe 로 통과 확인된 모델만.
# ---------------------------------------------------------------------------
IMAGE_MODELS: list[dict[str, str]] = [
    {"key": "Kling:2.1", "name": "Kling", "version": "2.1", "label": "Kling 2.1", "badge": "빠름"},
    {"key": "Kling:3.0", "name": "Kling", "version": "3.0", "label": "Kling 3.0", "badge": ""},
    {"key": "Seedream:4.5", "name": "Seedream", "version": "4.5", "label": "Seedream 4.5", "badge": ""},
    {"key": "Seedream:5.0-lite", "name": "Seedream", "version": "5.0-lite", "label": "Seedream 5.0 Lite", "badge": "최신"},
    {"key": "Qwen:0925", "name": "Qwen", "version": "0925", "label": "Qwen 0925", "badge": ""},
    {"key": "Jimeng:4.0", "name": "Jimeng", "version": "4.0", "label": "Jimeng 4.0", "badge": ""},
]

VIDEO_MODELS: list[dict[str, str]] = [
    {"key": "Kling:2.6", "name": "Kling", "version": "2.6", "label": "Kling 2.6", "badge": ""},
    {"key": "Kling:3.0", "name": "Kling", "version": "3.0", "label": "Kling 3.0", "badge": ""},
    {"key": "Kling:3.0-Omni", "name": "Kling", "version": "3.0-Omni", "label": "Kling 3.0 Omni", "badge": "최신"},
    {"key": "Kling:O1", "name": "Kling", "version": "O1", "label": "Kling O1", "badge": ""},
    {"key": "Hailuo:02", "name": "Hailuo", "version": "02", "label": "Hailuo 02", "badge": ""},
    {"key": "Hailuo:2.3", "name": "Hailuo", "version": "2.3", "label": "Hailuo 2.3", "badge": ""},
    {"key": "Mingmou:1.0", "name": "Mingmou", "version": "1.0", "label": "Mingmou 1.0", "badge": ""},
    {"key": "Vidu:q2", "name": "Vidu", "version": "q2", "label": "Vidu q2", "badge": ""},
    {"key": "Vidu:q3", "name": "Vidu", "version": "q3", "label": "Vidu q3", "badge": "최신"},
]


def parse_model_key(model_key: str) -> tuple[str, str]:
    """`Name:Version` 형식의 키를 (Name, Version) 으로 분해. 잘못된 키는 ValueError."""
    if ":" not in model_key:
        raise ValueError(f"잘못된 모델 키 (Name:Version 형식 필요): {model_key}")
    name, version = model_key.split(":", 1)
    if not name or not version:
        raise ValueError(f"잘못된 모델 키: {model_key}")
    return name, version


__all__ = [
    "create_image_task",
    "describe_image_task",
    "create_video_task",
    "describe_video_task",
    "IMAGE_MODELS",
    "VIDEO_MODELS",
    "parse_model_key",
]
