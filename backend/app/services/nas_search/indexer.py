"""인덱싱 파이프라인 + 진행률 싱글톤.

흐름:
walker → extractor.extract_text → chunk_text → embedder.embed_passages → DB upsert
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models.nas_file import NasFile, NasTextChunk
from app.services.nas_search.embedder import embed_passages
from app.services.nas_search.file_walker import WalkedFile, walk_changed_files
from app.services.nas_search.text_extractor import chunk_text, extract_text

logger = logging.getLogger(__name__)

# 동시 인덱싱 1개만 허용. asyncio.Lock은 모듈 레벨 전역.
_index_lock = asyncio.Lock()


@dataclass
class IndexProgress:
    """진행률 싱글톤. 라우터에서 그대로 직렬화해서 클라이언트에 노출."""

    running: bool = False
    processed: int = 0
    total: int = 0
    current_path: str | None = None
    errors: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None
    failures: list[str] = field(default_factory=list)

    def reset(self, total: int) -> None:
        self.running = True
        self.processed = 0
        self.total = total
        self.current_path = None
        self.errors = 0
        self.started_at = datetime.now(tz=timezone.utc)
        self.finished_at = None
        self.last_error = None
        self.failures = []

    def finish(self) -> None:
        self.running = False
        self.current_path = None
        self.finished_at = datetime.now(tz=timezone.utc)


# 모듈 전역 싱글톤. 프로세스가 살아있는 동안만 유효(다중 워커 환경은 추후 Redis로 이전).
INDEX_PROGRESS = IndexProgress()

# 요약 backfill 전용 진행률. 본 인덱싱(INDEX_PROGRESS)과 분리해 동시 실행 가능.
# Anthropic API rate limit이 별도 자원이라 충돌 없음. 락도 별도(_summary_lock).
SUMMARY_PROGRESS = IndexProgress()


def is_indexing() -> bool:
    return INDEX_PROGRESS.running


def is_summarizing() -> bool:
    return SUMMARY_PROGRESS.running


async def _upsert_nas_file(db: AsyncSession, wf: WalkedFile) -> NasFile:
    """경로 기준 upsert. 기존 청크는 caller가 별도로 비운다."""
    result = await db.execute(select(NasFile).where(NasFile.path == wf.path))
    nas_file = result.scalar_one_or_none()
    if nas_file is None:
        nas_file = NasFile(
            path=wf.path,
            name=wf.name,
            mime_type=wf.mime_type,
            file_type=wf.file_type,
            size_bytes=wf.size_bytes,
            mtime=wf.mtime,
            file_hash=wf.file_hash,
        )
        db.add(nas_file)
        await db.flush()
        return nas_file

    nas_file.name = wf.name
    nas_file.mime_type = wf.mime_type
    nas_file.file_type = wf.file_type
    nas_file.size_bytes = wf.size_bytes
    nas_file.mtime = wf.mtime
    nas_file.file_hash = wf.file_hash
    return nas_file


def path_relative_to_root(path: str, root: str) -> str:
    """NAS 마운트 root 기준 상대 경로. Windows backslash 정규화."""
    try:
        return os.path.relpath(path, root).replace("\\", "/")
    except ValueError:
        return os.path.basename(path)


def build_filename_header(name: str | None, path: str, root: str) -> str:
    """파일명 + 상대경로 헤더 청크 (v0.6.7).

    본문 추출 실패 파일도 파일명만으로 검색 가능하게 하기 위함.
    """
    rel = path_relative_to_root(path, root)
    return f"{name or ''} ({rel})".strip()


async def _process_one(db: AsyncSession, wf: WalkedFile) -> None:
    """파일 1건을 트랜잭션으로 처리. 실패 시 last_error 기록 후 caller에 예외 전파."""
    # PDF/DOCX/PPTX 파싱은 sync + SSHFS 네트워크 I/O라 이벤트 루프를 막지 않게 스레드로.
    text = await asyncio.to_thread(extract_text, wf.path)
    nas_file = await _upsert_nas_file(db, wf)

    # v0.6.7: 파일명 + 상대경로를 본문 앞에 prepend.
    # 본문 추출 실패해도 파일명만으로도 검색 결과에 노출됨 (7,648개 추출 실패 파일 회수).
    filename_header = build_filename_header(wf.name, wf.path, settings.nas_mount_path)
    full_text = f"{filename_header}\n\n{text}" if text else filename_header

    chunks = chunk_text(
        full_text,
        chunk_chars=max(500, settings.nas_index_chunk_size * 3),
        overlap_chars=max(50, settings.nas_index_chunk_overlap * 3),
    )
    if not chunks:
        nas_file.indexed_at = datetime.now(tz=timezone.utc)
        nas_file.last_error = "청크 분할 결과가 비어있음"
        await db.execute(delete(NasTextChunk).where(NasTextChunk.file_id == nas_file.id))
        return

    # 임베딩은 동기 CPU 작업이므로 스레드 풀로 우회해 이벤트 루프를 막지 않는다.
    vectors = await asyncio.to_thread(embed_passages, chunks)

    # 기존 청크 삭제 후 새 청크 적재 (가장 단순한 재인덱싱 정책).
    await db.execute(delete(NasTextChunk).where(NasTextChunk.file_id == nas_file.id))
    for idx, (content, vec) in enumerate(zip(chunks, vectors)):
        db.add(
            NasTextChunk(
                file_id=nas_file.id,
                chunk_index=idx,
                content=content,
                embedding=vec.tolist(),
                token_count=len(content),
            )
        )
    nas_file.indexed_at = datetime.now(tz=timezone.utc)
    nas_file.last_error = None if text else "본문 추출 실패 — 파일명 청크만 색인됨 (v0.6.7)"


async def _record_failure(path: str, message: str) -> None:
    """파일 단위 실패를 별도 세션으로 기록. 본 트랜잭션과 분리."""
    async with async_session() as db:
        result = await db.execute(select(NasFile).where(NasFile.path == path))
        nas_file = result.scalar_one_or_none()
        if nas_file is not None:
            nas_file.last_error = message[:1000]
            await db.commit()


def _resolve_scan_root(root: str, subdir: str | None) -> str:
    """root + subdir이 root 안에 있는지 검증 후 절대 경로 반환. path traversal 방어."""
    if not subdir:
        return root
    candidate = os.path.realpath(os.path.join(root, subdir))
    root_real = os.path.realpath(root)
    try:
        if os.path.commonpath([candidate, root_real]) != root_real:
            raise ValueError(f"subdir이 root를 벗어남: {subdir}")
    except ValueError as exc:
        raise ValueError(f"subdir 경로 검증 실패: {subdir}") from exc
    return candidate


async def _run_pipeline(*, full_rescan: bool, subdir: str | None) -> None:
    """실제 인덱싱 본체. 락은 caller가 잡는다."""
    root = settings.nas_mount_path
    scan_root = _resolve_scan_root(root, subdir)
    async with async_session() as db:
        targets = await walk_changed_files(
            db,
            scan_root,
            full_rescan=full_rescan,
            max_file_mb=settings.nas_index_max_file_mb,
        )

    INDEX_PROGRESS.reset(total=len(targets))
    logger.info(
        "NAS 인덱싱 시작 — 대상 %d개 파일 (scan_root=%s, full_rescan=%s)",
        len(targets),
        scan_root,
        full_rescan,
    )

    for wf in targets:
        INDEX_PROGRESS.current_path = wf.path
        try:
            async with async_session() as db:
                await _process_one(db, wf)
                await db.commit()
        except Exception as exc:  # noqa: BLE001
            INDEX_PROGRESS.errors += 1
            INDEX_PROGRESS.last_error = f"{wf.path}: {exc}"
            INDEX_PROGRESS.failures.append(INDEX_PROGRESS.last_error)
            logger.exception("파일 인덱싱 실패: %s", wf.path)
            try:
                await _record_failure(wf.path, str(exc))
            except Exception:  # noqa: BLE001
                logger.exception("실패 사유 기록 중 추가 오류")
        finally:
            INDEX_PROGRESS.processed += 1


async def run_indexing(
    *, full_rescan: bool = False, subdir: str | None = None
) -> None:
    """라우터 백그라운드 태스크에서 호출하는 진입점.

    subdir 지정 시 NAS_MOUNT_PATH 하위 일부만 walk (검색/다운로드는 root 기준 그대로).
    동시 1개만 실행. 이미 진행 중이면 RuntimeError.
    """
    if _index_lock.locked():
        raise RuntimeError("이미 인덱싱이 진행 중입니다")
    async with _index_lock:
        try:
            await _run_pipeline(full_rescan=full_rescan, subdir=subdir)
        finally:
            INDEX_PROGRESS.finish()
            logger.info(
                "NAS 인덱싱 종료 — 처리 %d/%d, 실패 %d",
                INDEX_PROGRESS.processed,
                INDEX_PROGRESS.total,
                INDEX_PROGRESS.errors,
            )
