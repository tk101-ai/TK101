"""텐센트 임시 스토리지 URL → NAS RW 마운트로 다운로드.

텐센트 vod 임시 URL 은 7일 만료. 그 전에 NAS 로 복사해서 영구 보관.
저장 위치는 ``settings.playground_media_root`` (라이브 환경은 NAS RW 마운트
``/mnt/nas-rw/playground``, 사용자가 NAS DSM 에서 직접 보고 관리 가능).

저장 경로 패턴 (2026-06-18 날짜 세그먼트 보강):
    {root}/{department}/{user_id}/{YYYY-MM-DD}/{kind}/{task_id}.{ext}

- 사용자 의도: 1차 부서 단위, 2차 사용자 단위, 3차 생성 날짜 폴더. NAS DSM 에서 직관적으로 탐색.
- ext 는 URL 의 파일 확장자 그대로 (없으면 image=png, video=mp4 fallback).
- 디렉토리는 자동 생성.
- 절대 경로는 DB(playground_media.file_path)에 저장되므로 과거 파일은 영향 없음.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
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


def _sanitize_segment(value: str) -> str:
    """경로 세그먼트를 파일시스템 안전 문자로 제한 (NAS 호환)."""
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", value).strip(".")
    return safe or "unknown"


async def download_media(
    *,
    url: str,
    user_id: uuid.UUID,
    department: str | None,
    task_id: str,
    kind: str,
) -> str | None:
    """텐센트 결과 URL 을 NAS RW 마운트로 다운로드 → 절대 경로 반환. 실패 시 None.

    이미 같은 파일이 있으면 덮어쓰지 않고 기존 경로 반환 (idempotent).
    경로: ``{root}/{department}/{user_id}/{YYYY-MM-DD}/{kind}/{task_id}.{ext}``
    """
    ext = _guess_ext(url, kind)
    dept = _sanitize_segment(department or "unknown")
    # 생성 날짜(UTC) 세그먼트 — 갤러리 날짜별 그룹핑과 동일한 기준.
    date_seg = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    user_dir = _safe_root() / dept / str(user_id) / date_seg / kind
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
