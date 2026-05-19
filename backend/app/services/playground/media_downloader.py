"""텐센트 임시 스토리지 URL → 백엔드 디스크로 다운로드.

텐센트 vod 임시 URL 은 7일 만료. 그 전에 우리 서버 디스크로 복사해서 영구 보관.
저장 위치는 ``settings.playground_media_root`` (docker volume mount 권장).

저장 경로 패턴:
    {root}/{user_id}/{kind}/{task_id}.{ext}

- ext 는 URL 의 파일 확장자 그대로 (없으면 image=png, video=mp4 fallback).
- 디렉토리는 자동 생성. 권한 0700 으로 만든다.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from pathlib import Path
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


_EXT_FALLBACK = {"image": "png", "video": "mp4"}


def _guess_ext(url: str, kind: str) -> str:
    path = urlparse(url).path
    name = os.path.basename(path)
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        # 단순 sanitize.
        if re.fullmatch(r"[a-z0-9]{1,8}", ext):
            return ext
    return _EXT_FALLBACK.get(kind, "bin")


def _safe_root() -> Path:
    root = Path(settings.playground_media_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


async def download_media(
    *,
    url: str,
    user_id: uuid.UUID,
    task_id: str,
    kind: str,
) -> str | None:
    """텐센트 결과 URL 을 디스크로 다운로드 → 절대 경로 반환. 실패 시 None.

    이미 같은 파일이 있으면 덮어쓰지 않고 기존 경로 반환 (idempotent).
    """
    ext = _guess_ext(url, kind)
    user_dir = _safe_root() / str(user_id) / kind
    user_dir.mkdir(parents=True, exist_ok=True)

    # task_id 에 슬래시 등이 들어갈 가능성 차단.
    safe_id = re.sub(r"[^A-Za-z0-9_.-]", "_", task_id)
    target = user_dir / f"{safe_id}.{ext}"
    if target.exists() and target.stat().st_size > 0:
        return str(target)

    try:
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            target.write_bytes(resp.content)
    except Exception as exc:  # noqa: BLE001
        logger.warning("media download 실패 (task=%s url=%s): %s", task_id, url, exc)
        return None

    logger.info(
        "media downloaded: task=%s kind=%s size=%d bytes path=%s",
        task_id,
        kind,
        target.stat().st_size,
        target,
    )
    return str(target)


__all__ = ["download_media"]
