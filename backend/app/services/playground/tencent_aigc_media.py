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
) -> dict[str, Any]:
    """Create image generation task. Returns {TaskId, RequestId}."""
    output_config: dict[str, Any] = {
        "StorageMode": "Temporary",
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
) -> dict[str, Any]:
    """Create video generation task. Returns {TaskId, RequestId}.

    ``input_image_url`` 가 주어지면 image-to-video (i2v) 모드.
    body 에 ``Input.FileInfos[0].FileUrl`` 을 추가한다. 텐센트 i2v 의 정확한
    필드명은 라이브 probe 가 안 끝나 추정치 — 라이브에서 400 이면
    필드명 (예: ``InputImage`` / ``ReferenceImage``) 변경 필요.
    """
    body: dict[str, Any] = {
        "SubAppId": int(settings.tencent_aigc_subapp_id),
        "ModelName": model_name,
        "ModelVersion": model_version,
        "Prompt": prompt,
        "EnhancePrompt": "Enabled" if enhance_prompt else "Disabled",
        "OutputConfig": {
            "StorageMode": "Temporary",
            "Duration": duration,
            "Resolution": resolution,
            "AspectRatio": aspect_ratio,
            "AudioGeneration": "Enabled" if audio_generation else "Disabled",
            "InputComplianceCheck": "Enabled",
            "OutputComplianceCheck": "Enabled",
        },
    }
    if input_image_url:
        # i2v(image-to-video): MPS 의 CreateAigcVideoTask (공개문서 1041/76487).
        # 입력 이미지는 top-level ``ImageUrl``(공개 URL). 출력은 **COS 버킷 필수**
        # (StoreCosParam) — 콘솔에서 버킷 생성 + MPS_QcsRole 승인 선행. 미설정이면
        # 출력처 없는 고아 task 가 생성돼 결과 조회 불가(ResourceNotFound) 이므로 막는다.
        if not settings.tencent_aigc_mps_cos_bucket or not settings.tencent_aigc_mps_cos_region:
            raise RuntimeError(
                "i2v(이미지→영상) 출력 COS 버킷 미설정 — 텐센트 콘솔에서 COS 버킷 생성 + "
                "MPS_QcsRole 역할 승인 후 DOCGEN/TENCENT_AIGC_MPS_COS_* 설정 필요(베타)."
            )
        mps_body: dict[str, Any] = {
            "ModelName": model_name,
            "ModelVersion": model_version,
            "Prompt": prompt,
            "ImageUrl": input_image_url,
            "Duration": duration,
            "ExtraParameters": {
                "Resolution": resolution,
                "AspectRatio": aspect_ratio,
            },
            # 출력 저장 — MPS 가 생성 영상을 이 COS 경로에 쓴다(필수).
            "StoreCosParam": {
                "CosBucketName": settings.tencent_aigc_mps_cos_bucket,
                "CosBucketRegion": settings.tencent_aigc_mps_cos_region,
                "CosBucketPath": settings.tencent_aigc_mps_cos_path,
            },
        }
        return await _call_mps_intl("CreateAigcVideoTask", mps_body)
    return await _call_vod_intl("CreateAigcVideoTask", body)


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
