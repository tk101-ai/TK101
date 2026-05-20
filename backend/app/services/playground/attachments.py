"""Playground 첨부 파일 처리 — 저장, 텍스트 추출, vision payload 빌더.

T8 Phase 6 (2026-05-20):
- 채팅 입력에 이미지/PDF/텍스트/DOCX 첨부 지원.
- 업로드 시점에 PDF/DOCX/텍스트는 본문 추출 → DB ``extracted_text`` 캐시.
- /chat 호출 시 attachment_ids 로 참조 → vision 모델이면 이미지 data URL 동봉,
  아니면 텍스트만 사용자 메시지 앞에 prepend.

저장 경로:
    ``{playground_media_root}/{department}/{user_id}/attachments/{file_id}.{ext}``
"""
from __future__ import annotations

import base64
import io
import logging
import mimetypes
import re
import uuid
from pathlib import Path
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------
# 첨부 1개 최대 크기 (20MB). vision 모델 대부분 5~20MB 한도.
MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
# 첨부 본문 추출 최대 문자 수 (LLM context 보호).
MAX_EXTRACTED_CHARS = 30_000
# 이미지 vision payload 시 한 변 최대 픽셀 (downscale).
MAX_IMAGE_DIMENSION = 2048

# 허용 MIME → kind 매핑.
_MIME_TO_KIND: dict[str, str] = {
    "image/png": "image",
    "image/jpeg": "image",
    "image/webp": "image",
    "image/gif": "image",
    "application/pdf": "pdf",
    "text/plain": "text",
    "text/markdown": "text",
    "text/csv": "text",
    "application/json": "text",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}

# 확장자 fallback (MIME 가 모호하거나 octet-stream 일 때).
_EXT_TO_KIND: dict[str, str] = {
    "png": "image",
    "jpg": "image",
    "jpeg": "image",
    "webp": "image",
    "gif": "image",
    "pdf": "pdf",
    "txt": "text",
    "md": "text",
    "csv": "text",
    "json": "text",
    "log": "text",
    "py": "text",
    "ts": "text",
    "tsx": "text",
    "js": "text",
    "html": "text",
    "xml": "text",
    "yaml": "text",
    "yml": "text",
    "docx": "docx",
}

# Vision 지원 모델 — 텐센트 OpenAI-compat 경로 기준.
# 라이브 확인 안된 모델은 보수적으로 제외. 추가 시 여기에 등록.
VISION_MODELS: set[str] = {
    "gpt-5-chat",
    "gpt-4.1",  # OpenAI 공식 vision 지원.
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite-preview",
}


def supports_vision(model: str | None) -> bool:
    return bool(model) and model in VISION_MODELS


# ---------------------------------------------------------------------------
# 분류
# ---------------------------------------------------------------------------
def detect_kind(filename: str, mime: str | None) -> str | None:
    """파일명/MIME 으로 kind 추론. 미지원이면 None."""
    if mime and mime in _MIME_TO_KIND:
        return _MIME_TO_KIND[mime]
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext in _EXT_TO_KIND:
        return _EXT_TO_KIND[ext]
    # MIME 추론 한 번 더.
    guessed, _ = mimetypes.guess_type(filename)
    if guessed and guessed in _MIME_TO_KIND:
        return _MIME_TO_KIND[guessed]
    return None


def _sanitize_segment(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", value).strip(".")
    return safe or "unknown"


def _sanitize_filename(filename: str) -> str:
    """경로 분리자 제거 + 길이 제한. UTF-8 한글은 보존."""
    base = Path(filename).name  # 디렉토리 제거.
    safe = re.sub(r"[\x00-\x1f<>:\"/\\|?*]", "_", base)
    return safe[:200] or "untitled"


def build_storage_path(
    *,
    user_id: uuid.UUID,
    department: str | None,
    file_id: uuid.UUID,
    filename: str,
) -> Path:
    """``{root}/{department}/{user_id}/attachments/{file_id}.{ext}`` 절대 경로 (디렉토리 자동 생성)."""
    root = Path(settings.playground_media_root)
    dept = _sanitize_segment(department or "unknown")
    target_dir = root / dept / str(user_id) / "attachments"
    target_dir.mkdir(parents=True, exist_ok=True)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    ext = re.sub(r"[^a-z0-9]", "", ext) or "bin"
    return target_dir / f"{file_id}.{ext}"


# ---------------------------------------------------------------------------
# 텍스트 추출
# ---------------------------------------------------------------------------
def extract_text_from_pdf(data: bytes) -> str:
    """pdfplumber 로 PDF 텍스트 추출. 빈 결과면 빈 문자열."""
    try:
        import pdfplumber  # type: ignore
    except ImportError:
        logger.warning("pdfplumber 미설치 — PDF 텍스트 추출 불가")
        return ""
    text_parts: list[str] = []
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                txt = page.extract_text() or ""
                if txt.strip():
                    text_parts.append(f"--- Page {i} ---\n{txt}")
                if sum(len(p) for p in text_parts) > MAX_EXTRACTED_CHARS:
                    text_parts.append("\n[... 분량 초과로 잘림 ...]")
                    break
    except Exception:
        logger.exception("PDF 텍스트 추출 실패")
        return ""
    return "\n\n".join(text_parts)[:MAX_EXTRACTED_CHARS]


def extract_text_from_docx(data: bytes) -> str:
    """python-docx 로 DOCX 본문 추출."""
    try:
        from docx import Document  # type: ignore
    except ImportError:
        logger.warning("python-docx 미설치 — DOCX 텍스트 추출 불가")
        return ""
    try:
        doc = Document(io.BytesIO(data))
        paras = [p.text for p in doc.paragraphs if p.text and p.text.strip()]
        joined = "\n".join(paras)
        return joined[:MAX_EXTRACTED_CHARS]
    except Exception:
        logger.exception("DOCX 텍스트 추출 실패")
        return ""


def extract_text_from_plain(data: bytes) -> str:
    """텍스트 파일을 utf-8 우선 + cp949 fallback 으로 디코드."""
    for enc in ("utf-8", "utf-8-sig", "cp949", "latin-1"):
        try:
            return data.decode(enc)[:MAX_EXTRACTED_CHARS]
        except UnicodeDecodeError:
            continue
    return ""


def extract_text(data: bytes, kind: str) -> str:
    if kind == "pdf":
        return extract_text_from_pdf(data)
    if kind == "docx":
        return extract_text_from_docx(data)
    if kind == "text":
        return extract_text_from_plain(data)
    return ""


# ---------------------------------------------------------------------------
# 이미지 → data URL (vision payload)
# ---------------------------------------------------------------------------
def build_image_data_url(path: Path, mime: str) -> str | None:
    """이미지 파일을 base64 data URL 로 변환. 너무 크면 Pillow 로 다운스케일."""
    try:
        data = path.read_bytes()
    except OSError:
        logger.exception("이미지 파일 읽기 실패: %s", path)
        return None

    # Pillow 가능하면 다운스케일 (모델 컨텍스트 절약 + 비용 감소).
    try:
        from PIL import Image  # type: ignore

        with Image.open(io.BytesIO(data)) as img:
            img.load()
            w, h = img.size
            if max(w, h) > MAX_IMAGE_DIMENSION:
                ratio = MAX_IMAGE_DIMENSION / max(w, h)
                new_size = (int(w * ratio), int(h * ratio))
                resized = img.resize(new_size, Image.LANCZOS)
                buf = io.BytesIO()
                fmt = "JPEG" if mime == "image/jpeg" else "PNG"
                save_kwargs: dict[str, Any] = {"format": fmt}
                if fmt == "JPEG":
                    if resized.mode != "RGB":
                        resized = resized.convert("RGB")
                    save_kwargs["quality"] = 85
                resized.save(buf, **save_kwargs)
                data = buf.getvalue()
                mime = "image/jpeg" if fmt == "JPEG" else "image/png"
    except ImportError:
        # Pillow 없으면 원본 그대로 인코딩.
        pass
    except Exception:
        logger.exception("이미지 다운스케일 실패 — 원본 사용")

    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------------------------------------------------------------------
# 사용자 메시지에 첨부 결합
# ---------------------------------------------------------------------------
def build_user_content(
    *,
    user_text: str,
    attachments: list[dict],
    model: str,
) -> str | list[dict]:
    """첨부가 있으면 OpenAI vision 표준 ``content`` 배열, 없으면 plain string.

    attachments 각 항목:
        {"kind": "image"|"pdf"|"text"|"docx", "filename": str, "mime": str,
         "file_path": str, "extracted_text": str | None}

    이미지: vision 모델이면 image_url 블록, 아니면 "[이미지 첨부: name (vision 미지원 모델)]" 안내문.
    PDF/text/docx: extracted_text 를 사용자 메시지 앞에 코드블록으로 prepend.
    """
    if not attachments:
        return user_text

    text_parts: list[str] = []
    image_blocks: list[dict] = []
    vision_ok = supports_vision(model)

    for att in attachments:
        kind = att.get("kind")
        name = att.get("filename") or "untitled"
        if kind == "image":
            if vision_ok:
                data_url = build_image_data_url(
                    Path(att["file_path"]), att.get("mime") or "image/png"
                )
                if data_url:
                    image_blocks.append(
                        {"type": "image_url", "image_url": {"url": data_url}}
                    )
                    continue
            # vision 미지원 → 안내 텍스트로 강등.
            text_parts.append(f"[이미지 첨부 '{name}' — 현재 모델이 vision 미지원]")
        elif kind in ("pdf", "text", "docx"):
            body = att.get("extracted_text") or ""
            if not body.strip():
                text_parts.append(f"[첨부 '{name}' — 본문 추출 결과 없음]")
                continue
            text_parts.append(
                f"=== 첨부 파일: {name} ===\n{body}\n=== 첨부 끝 ===\n"
            )

    prefix = "\n\n".join(text_parts)
    combined_text = f"{prefix}\n\n{user_text}" if prefix else user_text

    if not image_blocks:
        return combined_text

    # vision 블록이 하나라도 있으면 OpenAI 표준 content array.
    content: list[dict] = [{"type": "text", "text": combined_text}]
    content.extend(image_blocks)
    return content


__all__ = [
    "MAX_ATTACHMENT_BYTES",
    "MAX_EXTRACTED_CHARS",
    "VISION_MODELS",
    "supports_vision",
    "detect_kind",
    "build_storage_path",
    "extract_text",
    "build_image_data_url",
    "build_user_content",
]
