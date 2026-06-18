"""구조화 섹션 → .docx 바이트. 마크다운 표(| a | b |)는 워드 표로 변환."""
from __future__ import annotations

import io
import re


def _looks_like_table(block: str) -> bool:
    lines = [ln for ln in block.splitlines() if ln.strip()]
    return len(lines) >= 2 and all("|" in ln for ln in lines[:2])


def _add_markdown_table(doc, block: str) -> None:
    rows = [
        [c.strip() for c in ln.strip().strip("|").split("|")]
        for ln in block.splitlines()
        if ln.strip() and "|" in ln
    ]
    # 마크다운 구분선(---|---) 행 제거.
    rows = [r for r in rows if not all(set(c) <= {"-", ":", " "} and c for c in r)]
    if not rows:
        return
    ncol = max(len(r) for r in rows)
    table = doc.add_table(rows=len(rows), cols=ncol)
    table.style = "Light Grid Accent 1"
    for i, r in enumerate(rows):
        for j in range(ncol):
            table.cell(i, j).text = r[j] if j < len(r) else ""


def build_docx(title: str, sections: list[dict]) -> bytes:
    """title + sections([{heading, body}]) → .docx 바이트."""
    from docx import Document  # 지연 import (form_filler/renderer 패턴)

    doc = Document()
    doc.add_heading(title or "문서", level=0)
    for s in sections:
        heading = (s.get("heading") or "").strip()
        if heading:
            doc.add_heading(heading, level=1)
        body = (s.get("body") or "").strip()
        if not body:
            continue
        # 표 블록과 일반 문단을 분리 처리(빈 줄 기준).
        for block in re.split(r"\n\s*\n", body):
            block = block.strip()
            if not block:
                continue
            if _looks_like_table(block):
                _add_markdown_table(doc, block)
            else:
                for line in block.splitlines():
                    if line.strip():
                        doc.add_paragraph(line.strip())
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
