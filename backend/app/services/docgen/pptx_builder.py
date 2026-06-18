"""구조화 섹션 → .pptx 바이트. 제목 슬라이드 1장 + 섹션당 슬라이드(불릿)."""
from __future__ import annotations

import io
import re

# 슬라이드 본문 텍스트가 너무 길어 한 장을 넘치지 않도록 줄 수 상한.
_MAX_LINES_PER_SLIDE = 12


def _looks_like_table(block: str) -> bool:
    lines = [ln for ln in block.splitlines() if ln.strip()]
    return len(lines) >= 2 and all("|" in ln for ln in lines[:2])


def _table_rows(block: str) -> list[list[str]]:
    rows = [
        [c.strip() for c in ln.strip().strip("|").split("|")]
        for ln in block.splitlines()
        if ln.strip() and "|" in ln
    ]
    # 마크다운 구분선(---|---) 행 제거.
    return [r for r in rows if not all(set(c) <= {"-", ":", " "} and c for c in r)]


def _add_table_slide(prs, heading: str, rows: list[list[str]]) -> None:
    from pptx.util import Inches, Pt

    if not rows:
        return
    slide = prs.slides.add_slide(prs.slide_layouts[5])  # 제목만 있는 레이아웃.
    slide.shapes.title.text = heading or "표"
    ncol = max(len(r) for r in rows)
    nrow = len(rows)
    left, top = Inches(0.5), Inches(1.6)
    width, height = Inches(9.0), Inches(0.4 * nrow)
    table = slide.shapes.add_table(nrow, ncol, left, top, width, height).table
    for i, r in enumerate(rows):
        for j in range(ncol):
            cell = table.cell(i, j)
            cell.text = r[j] if j < len(r) else ""
            for para in cell.text_frame.paragraphs:
                para.font.size = Pt(12)


def _add_bullet_slide(prs, heading: str, lines: list[str]) -> None:
    from pptx.util import Pt

    slide = prs.slides.add_slide(prs.slide_layouts[1])  # 제목 + 내용 레이아웃.
    slide.shapes.title.text = heading or " "
    body = slide.placeholders[1].text_frame
    body.clear()
    for idx, line in enumerate(lines):
        para = body.paragraphs[0] if idx == 0 else body.add_paragraph()
        para.text = line
        para.level = 0
        para.font.size = Pt(16)


def _bullet_lines(block: str) -> list[str]:
    """문단 블록 → 슬라이드 불릿 줄 목록(마크다운 불릿 기호 제거)."""
    lines = []
    for line in block.splitlines():
        text = line.strip()
        if not text:
            continue
        text = re.sub(r"^[-*+]\s+", "", text)
        lines.append(text)
    return lines


def _add_section_slides(prs, heading: str, body: str) -> None:
    """섹션 본문을 표/불릿 슬라이드로 추가. 길면 여러 장으로 분할."""
    pending: list[str] = []

    def flush() -> None:
        nonlocal pending
        if pending:
            _add_bullet_slide(prs, heading, pending)
            pending = []

    # 표 블록과 일반 문단을 분리 처리(빈 줄 기준).
    for block in re.split(r"\n\s*\n", body):
        block = block.strip()
        if not block:
            continue
        if _looks_like_table(block):
            flush()
            _add_table_slide(prs, heading, _table_rows(block))
            continue
        for line in _bullet_lines(block):
            pending.append(line)
            if len(pending) >= _MAX_LINES_PER_SLIDE:
                flush()
    flush()


def build_pptx(title: str, sections: list[dict]) -> bytes:
    """title + sections([{heading, body}]) → .pptx 바이트."""
    from pptx import Presentation  # 지연 import (docx_builder 패턴).

    prs = Presentation()
    # 제목 슬라이드.
    cover = prs.slides.add_slide(prs.slide_layouts[0])
    cover.shapes.title.text = title or "문서"

    for s in sections:
        heading = (s.get("heading") or "").strip()
        body = (s.get("body") or "").strip()
        if not body:
            # 본문 없는 섹션도 제목만 한 장 남긴다.
            _add_bullet_slide(prs, heading, [])
            continue
        _add_section_slides(prs, heading, body)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
