"""PDF/DOCX/PPTX 텍스트 추출 + 단순 청크 분할.

PoC 단계라 tiktoken 없이 문자 기반 근사를 쓴다.
- chunk_size: 약 1500자(한국어 기준 약 500 token에 근접)
- chunk_overlap: 약 150자
"""
from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 문자 기반 청크 크기. token 환산은 모델별 편차가 커서 PoC에서는 단순화.
DEFAULT_CHUNK_CHARS = 1500
DEFAULT_OVERLAP_CHARS = 150


def extract_text(path: str) -> str:
    """확장자별 추출기 디스패치. 실패 시 빈 문자열 반환(상위 레이어가 skip 처리)."""
    ext = Path(path).suffix.lower()
    try:
        if ext == ".pdf":
            return _extract_pdf(path)
        if ext == ".docx":
            return _extract_docx(path)
        if ext == ".pptx":
            return _extract_pptx(path)
    except Exception as exc:  # noqa: BLE001 - 외부 라이브러리 다양한 예외 흡수
        logger.warning("텍스트 추출 실패: %s (%s)", path, exc)
        return ""
    logger.debug("지원하지 않는 확장자: %s", path)
    return ""


def _extract_pdf(path: str) -> str:
    from pdfminer.high_level import extract_text as pdf_extract

    return (pdf_extract(path) or "").strip()


def _extract_docx(path: str) -> str:
    from docx import Document

    doc = Document(path)
    parts: list[str] = []
    for para in doc.paragraphs:
        if para.text:
            parts.append(para.text)
    # 표 안의 텍스트도 인덱싱 대상에 포함.
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                if cell.text:
                    parts.append(cell.text)
    return "\n".join(parts).strip()


def _extract_pptx(path: str) -> str:
    from pptx import Presentation

    prs = Presentation(path)
    parts: list[str] = []
    for slide in prs.slides:
        for shape in slide.shapes:
            text = getattr(shape, "text", None)
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def chunk_text(
    text: str,
    *,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[str]:
    """텍스트를 chunk_chars 길이의 윈도우로 슬라이드. overlap만큼 겹쳐서 잘라냄.

    공백 정규화: 연속된 공백/개행을 단일 공백으로 압축해 청크 효율 향상.
    """
    if not text:
        return []
    if overlap_chars >= chunk_chars:
        overlap_chars = max(0, chunk_chars // 5)

    normalized = " ".join(text.split())
    if not normalized:
        return []

    chunks: list[str] = []
    start = 0
    length = len(normalized)
    step = chunk_chars - overlap_chars
    while start < length:
        end = min(start + chunk_chars, length)
        piece = normalized[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= length:
            break
        start += step
    return chunks
