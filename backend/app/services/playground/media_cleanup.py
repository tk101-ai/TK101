"""미디어 보존기간 자동 정리 (2026-06-18 추가).

``settings.playground_media_retention_days`` 를 경과한 ``playground_media`` 를
정리한다. 디스크 파일을 안전하게 삭제(unlink)하고 DB row 도 함께 제거한다.

만료 판정:
- ``expires_at`` 이 있으면 그 기준. (텐센트 임시 URL 만료일과는 별개로,
  폴링 시 ``created_at + 7일`` 로 채워진다 — 보존정책 cutoff 와 의미가 다르므로
  보존 기준은 항상 ``created_at + RETENTION_DAYS`` 를 1차 기준으로 삼고,
  필요 시 ``expires_at`` 도 고려한다.)
- 실제 보존 cutoff = ``now - RETENTION_DAYS``. ``created_at < cutoff`` 면 만료.

파일 삭제 안전장치:
- ``file_path`` 가 ``settings.playground_media_root`` 하위인지 검증(path traversal 차단).
- 존재할 때만 unlink. OS 오류는 로깅하고 계속(다음 row 처리).

트리거:
- ``POST /api/playground/admin/media/cleanup`` (require_admin) 수동 실행.
- backend lifespan 의 가벼운 주기 태스크(``run_media_cleanup_loop``) 자동 실행.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.playground import PlaygroundMedia

logger = logging.getLogger(__name__)

# 주기 태스크 실행 간격 (초). 보존정책은 일 단위라 하루 1회면 충분.
_CLEANUP_INTERVAL_SECONDS = 24 * 60 * 60


class CleanupResult(TypedDict):
    scanned: int
    deleted_rows: int
    deleted_files: int
    file_errors: int
    cutoff: datetime


def _is_within_media_root(file_path: str) -> bool:
    """file_path 가 media_root 하위 경로인지 검증 (path traversal 차단)."""
    media_root = os.path.abspath(settings.playground_media_root)
    real_path = os.path.abspath(file_path)
    return real_path == media_root or real_path.startswith(media_root + os.sep)


def _unlink_safely(file_path: str | None) -> bool:
    """검증된 경로의 파일을 안전하게 삭제. 삭제 성공 시 True.

    경로가 media_root 밖이면 건드리지 않고 False. OS 오류는 로깅 후 False.
    """
    if not file_path:
        return False
    if not _is_within_media_root(file_path):
        logger.warning("media cleanup: media_root 밖 경로 — 건너뜀: %s", file_path)
        return False
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
    except OSError as exc:
        logger.warning("media cleanup: 파일 삭제 실패 path=%s: %s", file_path, exc)
    return False


async def cleanup_expired_media(
    db: AsyncSession,
    *,
    retention_days: int | None = None,
) -> CleanupResult:
    """보존기간 경과 미디어 정리. 파일 unlink + DB row 삭제.

    실패(파일 삭제 오류 등)는 로깅하고 계속 진행해 가능한 만큼 정리한다.
    """
    days = (
        retention_days
        if retention_days is not None
        else settings.playground_media_retention_days
    )
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = select(PlaygroundMedia).where(PlaygroundMedia.created_at < cutoff)
    rows = (await db.execute(stmt)).scalars().all()

    deleted_files = 0
    file_errors = 0
    for row in rows:
        if row.file_path:
            if _unlink_safely(row.file_path):
                deleted_files += 1
            elif os.path.exists(row.file_path):
                # 경로는 존재하나 삭제 실패(권한/락 등).
                file_errors += 1
        await db.delete(row)

    await db.commit()

    result: CleanupResult = {
        "scanned": len(rows),
        "deleted_rows": len(rows),
        "deleted_files": deleted_files,
        "file_errors": file_errors,
        "cutoff": cutoff,
    }
    logger.info(
        "media cleanup 완료: scanned=%d deleted_rows=%d deleted_files=%d file_errors=%d cutoff=%s",
        result["scanned"],
        result["deleted_rows"],
        result["deleted_files"],
        result["file_errors"],
        cutoff.isoformat(),
    )
    return result


async def run_media_cleanup_loop(stop_event: asyncio.Event) -> None:
    """lifespan 주기 태스크: 하루 1회 보존기간 정리.

    기동 직후 1회 실행 후 ``_CLEANUP_INTERVAL_SECONDS`` 간격 반복. 한 회차 실패는
    로깅하고 다음 주기로 넘어간다. ``stop_event`` set 또는 cancel 시 종료.
    """
    from app.database import async_session

    while not stop_event.is_set():
        try:
            async with async_session() as db:
                await cleanup_expired_media(db)
        except Exception:  # noqa: BLE001 — 주기 태스크는 죽지 않고 다음 회차로.
            logger.exception("media cleanup 주기 태스크 실패 — 다음 주기 재시도")
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=_CLEANUP_INTERVAL_SECONDS)
        except asyncio.TimeoutError:
            continue


__all__ = ["CleanupResult", "cleanup_expired_media", "run_media_cleanup_loop"]
