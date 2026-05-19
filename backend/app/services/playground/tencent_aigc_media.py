"""Tencent AIGC Image/Video task 클라이언트 (T8 Phase 4/5 뼈대).

메모 (`업무개선요구사항/AI 플레이그라운드/API 호출 예시.txt`) 기준 호출 구조:

이미지:
    POST https://vod.intl.tencentcloudapi.com/
    Action=CreateAigcImageTask · TC3-HMAC-SHA256
    body = {SubAppId, ModelName, ModelVersion, Prompt, NegativePrompt?, EnhancePrompt?, OutputConfig}
    response = {Response: {TaskId, RequestId}}

영상:
    POST https://vod.intl.tencentcloudapi.com/
    Action=CreateAigcVideoTask · 동일 서명
    body = {SubAppId, ModelName, ModelVersion, Prompt, EnhancePrompt?, OutputConfig{Duration, Resolution, AspectRatio, ...}}
    response = {Response: {TaskId, RequestId}}

폴링:
    Action=DescribeAigcImageTask / DescribeAigcVideoTask
    body = {SubAppId, TaskId}
    response = {Response: {Status, OutputUrl?, ErrorMsg?, ...}}  (정확한 필드명은 텐센트 spec 미공개분 — 라이브 시험으로 확정)

뼈대 단계:
- DB 영속화 없음. 라우터가 task_id 를 그대로 반환, 프론트엔드가 폴링.
- 서명 헬퍼는 token_manager 의 ``_build_signed_headers`` 를 재사용 (텐센트 v3 표준).
- SecretId/Key/SubAppId 누락 시 RuntimeError → 라우터가 503 으로 응답.

운영 메모:
- 텐센트 콘솔에서 "액세스 키 관리" 페이지를 보면 SecretId 와 SecretKey 가 한 쌍으로 발급된다.
  SecretId 만 보고 그것이 SecretKey 라고 착각하지 말 것 — 두 값이 별도다.
- 모델 식별자(ModelName/ModelVersion) 는 텐센트 콘솔 "모델 카탈로그" 페이지의 정식 spec 기준.
  뼈대 단계에서는 메모 예시값(`GEM 3.1`, `Kling 3.0-Omni`) 을 기본값으로 둔다.
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
    payload = json.dumps(payload_obj, separators=(",", ":"), ensure_ascii=False)
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


# ---------------------------------------------------------------------------
# Image: CreateAigcImageTask
# ---------------------------------------------------------------------------
async def create_image_task(
    *,
    prompt: str,
    model_name: str = "GEM",
    model_version: str = "3.1",
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


async def describe_image_task(task_id: str) -> dict[str, Any]:
    """Image task 상태 조회."""
    body = {
        "SubAppId": int(settings.tencent_aigc_subapp_id),
        "TaskId": task_id,
    }
    return await _call_vod_intl("DescribeAigcImageTask", body)


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
) -> dict[str, Any]:
    """Create video generation task. Returns {TaskId, RequestId}."""
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
    return await _call_vod_intl("CreateAigcVideoTask", body)


async def describe_video_task(task_id: str) -> dict[str, Any]:
    """Video task 상태 조회."""
    body = {
        "SubAppId": int(settings.tencent_aigc_subapp_id),
        "TaskId": task_id,
    }
    return await _call_vod_intl("DescribeAigcVideoTask", body)


# ---------------------------------------------------------------------------
# 모델 카탈로그 — UI 노출용 (메모 예시 + 텐센트 PPT 추정 기준)
# 정식 spec 수령 후 식별자 미세 조정. 키/라벨 변경만으로 UI 자동 반영.
# ---------------------------------------------------------------------------
IMAGE_MODELS: list[dict[str, str]] = [
    {"key": "GEM:3.1", "name": "GEM", "version": "3.1", "label": "GEM 3.1", "badge": "메모 예시"},
    {"key": "GEM:3.0", "name": "GEM", "version": "3.0", "label": "GEM 3.0", "badge": ""},
]

VIDEO_MODELS: list[dict[str, str]] = [
    {"key": "Kling:3.0-Omni", "name": "Kling", "version": "3.0-Omni", "label": "Kling 3.0 Omni", "badge": "메모 예시"},
    {"key": "Kling:2.1", "name": "Kling", "version": "2.1", "label": "Kling 2.1", "badge": ""},
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
