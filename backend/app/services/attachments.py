"""거래 영수증 첨부 저장/조회/삭제 서비스.

저장 정책 (Wave 2 백엔드 D):
- 경로: /var/lib/transaction_attachments/{account_id}/{transaction_id}/{uuid}.{ext}
- 영구 저장은 호스트의 named volume에 매핑하는 것이 권장 사항이나,
  본 Wave 에서는 컨테이너 내부 디렉토리만 사용한다 (volume 추가는 사용자 결정).
  TODO: docker-compose.yml services.backend.volumes 에
        `transaction_attachments_data:/var/lib/transaction_attachments` 추가 권장.
- 확장자 화이트리스트 / 사이즈 제한 / Path traversal 방지 / atomic write 적용.
- 현재 Transaction.attachment_url 은 단건 컬럼이므로 사실상 1 거래 = 최신 1 파일.
  list 응답은 단건일 때도 list 로 반환하여 향후 다건 모델 도입 시 호환.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)


# 경로/확장자/사이즈 정책 ----------------------------------------------------
ATTACHMENT_BASE = Path("/var/lib/transaction_attachments")
ALLOWED_EXT = {".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".heic"}
MAX_SIZE = 10 * 1024 * 1024  # 10 MB

# HIGH-1: 파일 헤더 매직 바이트 화이트리스트.
# 확장자만 신뢰하면 .exe 를 .pdf 로 리네임해서 우회 가능 — 헤더로 더블 체크.
# heic 는 ftyp box 위치가 가변(앞 4바이트는 박스 크기)이라 검증 스킵.
_MAGIC_BYTES: dict[str, list[bytes]] = {
    ".pdf": [b"%PDF"],
    ".png": [b"\x89PNG\r\n\x1a\n"],
    ".jpg": [
        b"\xff\xd8\xff\xe0",
        b"\xff\xd8\xff\xe1",
        b"\xff\xd8\xff\xdb",
        b"\xff\xd8\xff\xee",
        b"\xff\xd8\xff\xe2",
        b"\xff\xd8\xff\xe3",
    ],
    ".jpeg": [
        b"\xff\xd8\xff\xe0",
        b"\xff\xd8\xff\xe1",
        b"\xff\xd8\xff\xdb",
        b"\xff\xd8\xff\xee",
        b"\xff\xd8\xff\xe2",
        b"\xff\xd8\xff\xe3",
    ],
    ".gif": [b"GIF87a", b"GIF89a"],
    # WebP: RIFF{4byte size}WEBP — RIFF + WEBP 둘 다 검증
    ".webp": [b"RIFF"],
}


def _verify_magic_bytes(ext: str, content: bytes) -> bool:
    """확장자별 헤더 매직 바이트 검증.

    .heic 등 정의되지 않은 확장자는 True (스킵). WebP 는 RIFF + 9~12바이트 WEBP 추가 확인.
    """
    expected = _MAGIC_BYTES.get(ext)
    if not expected:
        return True
    if not any(content.startswith(m) for m in expected):
        return False
    if ext == ".webp" and len(content) >= 12 and content[8:12] != b"WEBP":
        return False
    return True


# 파일명에서 제거할 위험 문자. 한글/공백/하이픈/언더스코어/괄호는 허용한다.
_FILENAME_SANITIZE_RE = re.compile(r"[^\w\s가-힣().\-_]", re.UNICODE)
_MULTI_SPACE_RE = re.compile(r"\s+")


# 도메인 예외 ----------------------------------------------------------------
class AttachmentError(Exception):
    """첨부 파일 처리 공통 예외 (라우터에서 HTTPException 으로 변환)."""

    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class AttachmentInfo:
    """첨부 파일 메타데이터 (응답용)."""

    filename: str
    size: int
    content_type: str | None
    uploaded_at: datetime
    relative_url: str  # Transaction.attachment_url 에 저장되는 값


# 내부 유틸 ------------------------------------------------------------------
def _sanitize_filename(original: str) -> str:
    """원본 파일명 → 안전한 표시용 파일명.

    한글/공백/괄호/점/하이픈/언더스코어 보존. 그 외 특수문자는 제거.
    빈 문자열이면 'attachment' 로 대체.
    """
    name = os.path.basename(original or "")
    name = name.replace("\\", "_")
    name = _FILENAME_SANITIZE_RE.sub("", name)
    name = _MULTI_SPACE_RE.sub(" ", name).strip()
    if not name or name in {".", ".."}:
        name = "attachment"
    return name[:200]


def _extract_ext(filename: str) -> str:
    """소문자 확장자 (점 포함)."""
    return Path(filename).suffix.lower()


def _account_dir(account_id: str) -> Path:
    return ATTACHMENT_BASE / str(account_id)


def _transaction_dir(account_id: str, transaction_id: str) -> Path:
    return _account_dir(account_id) / str(transaction_id)


def _resolve_safe(target: Path, base: Path) -> Path:
    """target 의 절대경로가 base 하위인지 검증한 뒤 반환.

    Path traversal (../..) / 심볼릭링크 우회 차단.
    """
    real_base = Path(os.path.realpath(base))
    real_target = Path(os.path.realpath(target))
    try:
        real_target.relative_to(real_base)
    except ValueError as exc:
        raise AttachmentError(
            "허용되지 않은 파일 경로입니다", status_code=403
        ) from exc
    return real_target


def _validate_filename_component(filename: str) -> None:
    """다운로드/삭제 시 호출. 경로 구분자/상위 디렉토리 토큰 차단."""
    if not filename:
        raise AttachmentError("파일명이 비어있습니다", status_code=400)
    if "\x00" in filename:
        raise AttachmentError("허용되지 않는 파일명입니다", status_code=400)
    if "/" in filename or "\\" in filename:
        raise AttachmentError(
            "허용되지 않는 파일명입니다 (경로 구분자 포함)", status_code=400
        )
    if filename in {".", ".."} or filename.startswith(".."):
        raise AttachmentError("허용되지 않는 파일명입니다", status_code=400)


# 공개 API --------------------------------------------------------------------
def save_attachment(
    account_id: str,
    transaction_id: str,
    file_bytes: bytes,
    original_filename: str,
    content_type: str | None = None,
) -> AttachmentInfo:
    """파일을 컨테이너 내부 영구 경로에 저장 후 메타데이터 반환.

    Raises:
        AttachmentError: 확장자 비허용, 크기 초과, 저장 실패 등.
    """
    size = len(file_bytes)
    if size == 0:
        raise AttachmentError("빈 파일입니다", status_code=400)
    if size > MAX_SIZE:
        raise AttachmentError(
            f"파일 크기가 제한을 초과했습니다 (최대 {MAX_SIZE // (1024 * 1024)}MB)",
            status_code=413,
        )

    safe_name = _sanitize_filename(original_filename)
    ext = _extract_ext(safe_name)
    if ext not in ALLOWED_EXT:
        allowed = ", ".join(sorted(ext.lstrip(".") for ext in ALLOWED_EXT))
        raise AttachmentError(
            f"허용되지 않은 파일 형식입니다 (허용: {allowed})",
            status_code=415,
        )

    # HIGH-1: 파일 헤더 매직 바이트 검증.
    # 확장자만 신뢰하면 mime spoofing 가능 (.exe → .pdf 리네임 등).
    if not _verify_magic_bytes(ext, file_bytes):
        raise AttachmentError(
            "파일 내용이 확장자와 일치하지 않습니다",
            status_code=415,
        )

    # 저장 디렉토리 준비
    txn_dir = _transaction_dir(account_id, transaction_id)
    try:
        txn_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        logger.error("첨부 디렉토리 생성 실패: %s", exc)
        raise AttachmentError(
            "파일 저장 디렉토리 생성에 실패했습니다", status_code=500
        ) from exc

    # 저장 파일명: {uuid8}_{sanitized}.ext  — uuid 로 충돌 방지 + 원본명 보존
    stored_filename = f"{uuid.uuid4().hex[:12]}_{safe_name}"
    target_path = txn_dir / stored_filename
    safe_target = _resolve_safe(target_path, ATTACHMENT_BASE)

    # Atomic write: 같은 디렉토리에 tempfile 작성 → rename
    tmp_fd, tmp_path_str = tempfile.mkstemp(
        prefix=".upload_", suffix=ext, dir=str(txn_dir)
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(tmp_fd, "wb") as fp:
            fp.write(file_bytes)
        os.replace(tmp_path, safe_target)
    except OSError as exc:
        logger.error("첨부 파일 저장 실패: %s", exc)
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise AttachmentError(
            "파일 저장 중 오류가 발생했습니다", status_code=500
        ) from exc

    relative_url = (
        f"/api/transactions/{transaction_id}/attachments/{stored_filename}"
    )
    return AttachmentInfo(
        filename=stored_filename,
        size=size,
        content_type=content_type,
        uploaded_at=datetime.now(timezone.utc),
        relative_url=relative_url,
    )


def get_attachment_path(
    account_id: str, transaction_id: str, filename: str
) -> Path:
    """안전한 파일 경로 조회. 존재하지 않으면 FileNotFoundError 가 아니라 AttachmentError(404)."""
    _validate_filename_component(filename)
    target = _transaction_dir(account_id, transaction_id) / filename
    safe_target = _resolve_safe(target, ATTACHMENT_BASE)
    if not safe_target.exists() or not safe_target.is_file():
        raise AttachmentError("첨부 파일을 찾을 수 없습니다", status_code=404)
    return safe_target


def list_attachments(account_id: str, transaction_id: str) -> list[AttachmentInfo]:
    """거래의 모든 첨부 메타 반환. 디렉토리가 없으면 빈 리스트."""
    txn_dir = _transaction_dir(account_id, transaction_id)
    if not txn_dir.exists():
        return []
    safe_dir = _resolve_safe(txn_dir, ATTACHMENT_BASE)
    items: list[AttachmentInfo] = []
    for entry in sorted(safe_dir.iterdir()):
        if not entry.is_file():
            continue
        if entry.name.startswith(".upload_"):
            # 미완성 tempfile — 무시
            continue
        try:
            stat = entry.stat()
        except OSError:
            continue
        items.append(
            AttachmentInfo(
                filename=entry.name,
                size=stat.st_size,
                content_type=None,
                uploaded_at=datetime.fromtimestamp(
                    stat.st_mtime, tz=timezone.utc
                ),
                relative_url=(
                    f"/api/transactions/{transaction_id}/attachments/{entry.name}"
                ),
            )
        )
    return items


def delete_attachment(
    account_id: str, transaction_id: str, filename: str
) -> None:
    """단일 파일 삭제. 존재하지 않으면 AttachmentError(404)."""
    target = get_attachment_path(account_id, transaction_id, filename)
    try:
        target.unlink()
    except OSError as exc:
        logger.error("첨부 삭제 실패: %s", exc)
        raise AttachmentError(
            "파일 삭제 중 오류가 발생했습니다", status_code=500
        ) from exc

    # 거래 디렉토리가 비었으면 정리 (선택). 실패해도 무시.
    txn_dir = _transaction_dir(account_id, transaction_id)
    try:
        if txn_dir.exists() and not any(txn_dir.iterdir()):
            shutil.rmtree(txn_dir, ignore_errors=True)
    except OSError:
        pass
