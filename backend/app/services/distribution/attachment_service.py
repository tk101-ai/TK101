"""T9 메시지 첨부 파일 서비스 (2026-05-26 추가).

저장 경로:
    ``{distribution_attachment_dir}/{session_id}/{message_id}.{ext}``

운영에선 ``/mnt/nas-rw/distribution/attachments/...`` 로 NAS DSM 에서 직접 조회 가능.

분류:
- 이미지 확장자/MIME 면 ``kind='image'`` — 텔레그램 미리보기 가능.
- 그 외(PDF/엑셀/한글 등) 는 ``kind='document'`` — 송신 시 force_document=True.

거부 항목:
- 화이트리스트에 없는 확장자.
- ``distribution_attachment_max_bytes`` 초과.
"""
from __future__ import annotations

import logging
import mimetypes
import os
import re
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from app.config import settings

logger = logging.getLogger(__name__)


_IMAGE_EXTS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".gif"}
)
_DOCUMENT_EXTS: frozenset[str] = frozenset(
    {
        ".pdf",
        ".xlsx",
        ".xls",
        ".csv",
        ".hwp",
        ".hwpx",
        ".docx",
        ".doc",
        ".pptx",
        ".ppt",
        ".txt",
    }
)
ALLOWED_EXTS: frozenset[str] = _IMAGE_EXTS | _DOCUMENT_EXTS

# 파일명 새니타이즈 — 디렉토리 트래버설/제어문자 차단.
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._\-가-힣 ]")


class AttachmentError(Exception):
    """첨부 처리 실패. ``status_code`` 로 HTTP 매핑."""

    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class SavedAttachment:
    """저장 결과."""

    path: str
    filename: str
    mime: str
    kind: str  # 'image' | 'document'
    size_bytes: int


def _classify(ext: str, mime: str | None) -> str:
    """확장자 + MIME 으로 ``image`` / ``document`` 결정."""
    if ext.lower() in _IMAGE_EXTS:
        return "image"
    if mime and mime.startswith("image/"):
        return "image"
    return "document"


def _sanitize_filename(name: str) -> str:
    """파일명에서 위험 문자 제거. 빈 문자열이면 'file' 로 폴백."""
    base = os.path.basename(name).strip()
    base = _SAFE_NAME_RE.sub("_", base)
    return base or "file"


def save_attachment(
    *,
    session_id: UUID,
    message_id: UUID,
    file_bytes: bytes,
    original_filename: str,
    content_type: str | None,
) -> SavedAttachment:
    """업로드된 파일을 NAS RW 에 저장하고 메타데이터 반환.

    실패 시 ``AttachmentError`` 발생 (HTTP 매핑은 라우터에서).
    """
    if not file_bytes:
        raise AttachmentError("빈 파일은 업로드할 수 없습니다.", status_code=400)

    max_bytes = settings.distribution_attachment_max_bytes
    if len(file_bytes) > max_bytes:
        raise AttachmentError(
            f"첨부 파일 크기가 한도({max_bytes // (1024 * 1024)} MB)를 초과합니다.",
            status_code=413,
        )

    safe_name = _sanitize_filename(original_filename)
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in ALLOWED_EXTS:
        raise AttachmentError(
            f"허용되지 않는 파일 형식입니다: {ext or '확장자 없음'}",
            status_code=415,
        )

    mime = content_type or mimetypes.guess_type(safe_name)[0] or "application/octet-stream"
    kind = _classify(ext, mime)

    base_dir = Path(settings.distribution_attachment_dir) / str(session_id)
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # NAS RW 마운트 실패 등 — 사용자에게 NAS 상태 확인 안내.
        logger.exception("첨부 디렉토리 생성 실패 — dir=%s", base_dir)
        raise AttachmentError(
            "첨부 저장 경로를 생성할 수 없습니다. NAS 마운트를 확인하세요.",
            status_code=503,
        ) from exc

    # 동일 message_id 에 대한 재업로드는 덮어쓰기 (1메시지 1첨부 가정).
    target = base_dir / f"{message_id}{ext}"
    try:
        with open(target, "wb") as fh:
            fh.write(file_bytes)
        os.chmod(target, 0o640)
    except OSError as exc:
        logger.exception("첨부 저장 실패 — path=%s", target)
        raise AttachmentError(
            "첨부 파일 저장에 실패했습니다.", status_code=500
        ) from exc

    logger.info(
        "첨부 저장 완료 — session=%s message=%s size=%d kind=%s",
        session_id,
        message_id,
        len(file_bytes),
        kind,
    )
    return SavedAttachment(
        path=str(target),
        filename=safe_name,
        mime=mime,
        kind=kind,
        size_bytes=len(file_bytes),
    )


def delete_attachment(path: str | None) -> bool:
    """저장된 첨부 파일 삭제. 파일이 없어도 True 반환 (idempotent)."""
    if not path:
        return True
    try:
        p = Path(path)
        if p.is_file():
            p.unlink()
            logger.info("첨부 삭제 — path=%s", path)
    except OSError:
        logger.exception("첨부 삭제 실패 — path=%s", path)
        return False
    return True


def is_safe_path(path: str) -> bool:
    """저장 디렉토리 밖 경로 접근 차단 (다운로드 핸들러에서 사용)."""
    try:
        base = Path(settings.distribution_attachment_dir).resolve()
        target = Path(path).resolve()
        return base in target.parents or target == base
    except (OSError, ValueError):
        return False
