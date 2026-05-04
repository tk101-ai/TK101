"""NAS 디렉토리 워크 + 변경 감지.

전략:
- NAS_MOUNT_PATH 하위를 재귀 탐색
- 지원 확장자(.pdf .docx .pptx)만 yield
- size/mtime/hash로 변경 여부 판정 → 미변경 파일은 스킵
"""
from __future__ import annotations

import asyncio
import dataclasses
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

# Synology / macOS 메타 디렉토리 — 인덱싱 대상 아님.
# #recycle: DSM 휴지통, @eaDir: Synology 썸네일/메타, .Trashes/.Spotlight-V100/.AppleDouble: macOS
EXCLUDED_DIR_NAMES = {
    "#recycle",
    "@eaDir",
    ".AppleDouble",
    ".Spotlight-V100",
    ".Trashes",
    ".TemporaryItems",
    "@Recycle",
}


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
    """root 아래 재귀 탐색. 지원 확장자만 yield. EXCLUDED_DIR_NAMES는 진입조차 안 함."""
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # in-place 수정으로 os.walk가 제외 디렉토리에 내려가지 않게 한다.
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
        for fname in filenames:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SUPPORTED_DOCUMENT_EXTS:
                yield os.path.join(dirpath, fname)


def _stat_file_no_hash(path: str) -> WalkedFile | None:
    """stat만 — hash는 변경 결정 후에 따로 채운다 (1MB 읽기 비용 회피)."""
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
        file_hash="",  # 변경 처리 시 _fill_hash로 채움
        file_type="document",
    )


def _fill_hash(wf: WalkedFile) -> WalkedFile:
    """WalkedFile의 file_hash 채워서 새 인스턴스 반환. frozen dataclass라 replace 사용."""
    return dataclasses.replace(wf, file_hash=_hash_first_chunk(wf.path))


def _collect_candidates(root: str, max_bytes: int) -> list[WalkedFile]:
    """sync 헬퍼: walk + stat (hash 제외, hash는 변경 결정 후 채움).

    SSHFS 네트워크 I/O라 caller가 asyncio.to_thread로 감싸야 한다.
    """
    candidates: list[WalkedFile] = []
    for path in _iter_candidate_files(root):
        wf = _stat_file_no_hash(path)
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
    return candidates


def _fill_hashes(targets: list[WalkedFile]) -> list[WalkedFile]:
    """변경 후보들에만 hash 일괄 계산. sync I/O이므로 caller가 to_thread로 감싼다."""
    return [_fill_hash(wf) for wf in targets]


async def walk_changed_files(
    db: AsyncSession,
    root: str,
    *,
    full_rescan: bool = False,
    max_file_mb: int = 50,
) -> list[WalkedFile]:
    """root 아래에서 새 파일 또는 변경된 파일만 반환 (hash 채움).

    1차 필터는 mtime + size 비교 (1MB hash 읽기 회피 → 변경 감지 비용 ~10배 절감).
    full_rescan=True면 모든 지원 파일을 변경 대상으로 처리.
    """
    if not await asyncio.to_thread(os.path.isdir, root):
        logger.warning("NAS 마운트 경로가 디렉토리가 아님: %s", root)
        return []

    max_bytes = max_file_mb * 1024 * 1024
    # SSHFS 네트워크 I/O가 이벤트 루프를 막지 않도록 워커 스레드에서 walk 수행.
    candidates = await asyncio.to_thread(_collect_candidates, root, max_bytes)

    if full_rescan:
        # 전체 재인덱싱 — 모든 파일에 hash 채움.
        return await asyncio.to_thread(_fill_hashes, candidates)

    # 기존 NasFile DB와 (mtime, size) 비교 — hash 안 봄 (1MB 읽기 회피).
    existing_rows = await db.execute(
        select(NasFile.path, NasFile.mtime, NasFile.size_bytes)
    )
    existing: dict[str, tuple[datetime | None, int | None]] = {
        row.path: (row.mtime, row.size_bytes) for row in existing_rows.all()
    }

    changed_no_hash: list[WalkedFile] = []
    for wf in candidates:
        prev = existing.get(wf.path)
        if prev is None:
            changed_no_hash.append(wf)
            continue
        prev_mtime, prev_size = prev
        if prev_size != wf.size_bytes or prev_mtime != wf.mtime:
            changed_no_hash.append(wf)

    # 변경된 파일에만 hash 채움 (확인용 + DB 기록).
    return await asyncio.to_thread(_fill_hashes, changed_no_hash)
