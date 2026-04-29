"""NAS 디렉토리 워크 + 변경 감지.

전략:
- NAS_MOUNT_PATH 하위를 재귀 탐색
- 지원 확장자(.pdf .docx .pptx)만 yield
- size/mtime/hash로 변경 여부 판정 → 미변경 파일은 스킵
"""
from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.nas_file import NasFile

logger = logging.getLogger(__name__)

SUPPORTED_DOCUMENT_EXTS = {".pdf", ".docx", ".pptx"}
HASH_SAMPLE_BYTES = 1024 * 1024  # 처음 1MB만 SHA1 해시 (큰 파일 비용 회피)


@dataclass(frozen=True)
class WalkedFile:
    """파일 워크 결과 1건. NasFile 행과 1:1 매핑되는 메타."""

    path: str
    name: str
    size_bytes: int
    mtime: datetime
    file_hash: str
    file_type: str  # 'document'

    @property
    def mime_type(self) -> str | None:
        ext = Path(self.path).suffix.lower()
        return {
            ".pdf": "application/pdf",
            ".docx": (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
            ".pptx": (
                "application/vnd.openxmlformats-officedocument.presentationml.presentation"
            ),
        }.get(ext)


def _hash_first_chunk(path: str, sample_bytes: int = HASH_SAMPLE_BYTES) -> str:
    """파일 처음 sample_bytes 바이트의 SHA1. 큰 파일에서도 빠르게 변경 감지."""
    h = hashlib.sha1()
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(sample_bytes)
            h.update(chunk)
    except OSError as exc:
        logger.warning("해시 계산 실패: %s (%s)", path, exc)
        return ""
    return h.hexdigest()


def _iter_candidate_files(root: str) -> Iterator[str]:
    """root 아래 재귀 탐색. 지원 확장자만 yield."""
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SUPPORTED_DOCUMENT_EXTS:
                yield os.path.join(dirpath, fname)


def _stat_file(path: str) -> WalkedFile | None:
    try:
        st = os.stat(path)
    except OSError as exc:
        logger.warning("stat 실패: %s (%s)", path, exc)
        return None
    return WalkedFile(
        path=path,
        name=os.path.basename(path),
        size_bytes=st.st_size,
        mtime=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc),
        file_hash=_hash_first_chunk(path),
        file_type="document",
    )


async def walk_changed_files(
    db: AsyncSession,
    root: str,
    *,
    full_rescan: bool = False,
    max_file_mb: int = 50,
) -> list[WalkedFile]:
    """root 아래에서 새 파일 또는 변경된 파일만 반환.

    full_rescan=True면 모든 지원 파일을 변경 대상으로 처리.
    """
    if not os.path.isdir(root):
        logger.warning("NAS 마운트 경로가 디렉토리가 아님: %s", root)
        return []

    max_bytes = max_file_mb * 1024 * 1024
    candidates: list[WalkedFile] = []
    for path in _iter_candidate_files(root):
        wf = _stat_file(path)
        if wf is None:
            continue
        if wf.size_bytes > max_bytes:
            logger.info(
                "용량 초과로 스킵: %s (%d MB)",
                path,
                wf.size_bytes // (1024 * 1024),
            )
            continue
        candidates.append(wf)

    if full_rescan:
        return candidates

    # 기존 NasFile DB와 (path, file_hash, size, mtime) 비교해 변경 항목만 추림.
    existing_rows = await db.execute(select(NasFile.path, NasFile.file_hash, NasFile.size_bytes))
    existing: dict[str, tuple[str | None, int | None]] = {
        row.path: (row.file_hash, row.size_bytes) for row in existing_rows.all()
    }

    changed: list[WalkedFile] = []
    for wf in candidates:
        prev = existing.get(wf.path)
        if prev is None:
            changed.append(wf)
            continue
        prev_hash, prev_size = prev
        if prev_hash != wf.file_hash or prev_size != wf.size_bytes:
            changed.append(wf)
    return changed
