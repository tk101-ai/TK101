"""섹션 body(마크다운) → 구조 블록 파서. pptx/docx 빌더 공용.

LLM이 body에 넣는 문단/불릿/표/차트를 디자인 렌더링이 가능한 블록 목록으로 변환한다.
지원 블록:
- paragraph : 일반 문단(여러 줄)
- bullets   : 불릿 목록. items=[(level, text)] (들여쓰기/중첩 단계 보존)
- table     : 마크다운 표 → rows=[[cell, ...]]
- chart     : ```chart {json} ``` 펜스 → data={type, title, categories, series}

차트 JSON 예:
    {"type":"bar","title":"분기 매출","categories":["1Q","2Q"],
     "series":[{"name":"매출","values":[10,14]}]}
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_BULLET_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
_CHART_FENCE_RE = re.compile(r"^```chart\s*$", re.IGNORECASE)
_FENCE_END_RE = re.compile(r"^```\s*$")
# 굵게(**...**) 마크업 — 셀/제목 정리용. 렌더러는 평문만 쓰므로 기호 제거.
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

_VALID_CHART_TYPES = {"bar", "column", "line", "pie"}


@dataclass
class Block:
    kind: str                                   # paragraph | bullets | table | chart
    lines: list[str] = field(default_factory=list)        # paragraph
    items: list[tuple[int, str]] = field(default_factory=list)  # bullets (level, text)
    rows: list[list[str]] = field(default_factory=list)   # table
    data: dict | None = None                              # chart


def strip_inline(text: str) -> str:
    """인라인 마크다운 기호 제거(평문 렌더용). 굵게/기울임/코드 백틱 정리."""
    text = _BOLD_RE.sub(r"\1", text)
    text = text.replace("`", "")
    return text.strip()


def _is_table_line(line: str) -> bool:
    return "|" in line and line.strip().startswith(("|", "")) and line.count("|") >= 1


def _looks_like_table(lines: list[str]) -> bool:
    real = [ln for ln in lines if ln.strip()]
    return len(real) >= 2 and all("|" in ln for ln in real[:2])


def _parse_table(lines: list[str]) -> list[list[str]]:
    rows = [
        [strip_inline(c) for c in ln.strip().strip("|").split("|")]
        for ln in lines
        if ln.strip() and "|" in ln
    ]
    # 마크다운 구분선(---|:--:) 행 제거.
    return [r for r in rows if not all(set(c) <= {"-", ":", " "} and c for c in r)]


def _level_from_indent(indent: str) -> int:
    """선행 공백/탭 → 불릿 레벨(2칸 또는 1탭 = 1단계). 최대 4단계."""
    spaces = indent.replace("\t", "  ")
    return min(len(spaces) // 2, 4)


def _parse_chart(payload: str) -> dict | None:
    """차트 펜스 본문(JSON) → 정규화 dict. 형식 불량이면 None."""
    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    ctype = str(raw.get("type") or "bar").lower()
    if ctype not in _VALID_CHART_TYPES:
        ctype = "bar"
    cats = [str(c) for c in (raw.get("categories") or [])]
    series = []
    for s in raw.get("series") or []:
        if not isinstance(s, dict):
            continue
        vals = []
        for v in s.get("values") or []:
            try:
                vals.append(float(v))
            except (TypeError, ValueError):
                vals.append(0.0)
        if vals:
            series.append({"name": str(s.get("name") or ""), "values": vals})
    if not cats or not series:
        return None
    return {"type": ctype, "title": str(raw.get("title") or ""), "categories": cats, "series": series}


def parse_blocks(body: str) -> list[Block]:
    """body 마크다운 → Block 목록(라인 기반 상태 머신)."""
    blocks: list[Block] = []
    lines = (body or "").splitlines()
    i, n = 0, len(lines)
    para: list[str] = []
    bullets: list[tuple[int, str]] = []

    def flush_para() -> None:
        if para:
            blocks.append(Block(kind="paragraph", lines=para[:]))
            para.clear()

    def flush_bullets() -> None:
        if bullets:
            blocks.append(Block(kind="bullets", items=bullets[:]))
            bullets.clear()

    while i < n:
        line = lines[i]
        stripped = line.strip()

        # 차트 펜스.
        if _CHART_FENCE_RE.match(stripped):
            flush_para()
            flush_bullets()
            payload: list[str] = []
            i += 1
            while i < n and not _FENCE_END_RE.match(lines[i].strip()):
                payload.append(lines[i])
                i += 1
            i += 1  # 닫는 ``` 소비.
            data = _parse_chart("\n".join(payload))
            if data:
                blocks.append(Block(kind="chart", data=data))
            continue

        # 빈 줄 → 누적 문단/불릿 종료.
        if not stripped:
            flush_para()
            flush_bullets()
            i += 1
            continue

        # 표 영역(연속된 | 라인) 수집.
        if "|" in line:
            tbl: list[str] = []
            j = i
            while j < n and "|" in lines[j] and lines[j].strip():
                tbl.append(lines[j])
                j += 1
            if _looks_like_table(tbl):
                flush_para()
                flush_bullets()
                blocks.append(Block(kind="table", rows=_parse_table(tbl)))
                i = j
                continue

        # 불릿.
        m = _BULLET_RE.match(line)
        if m:
            flush_para()
            bullets.append((_level_from_indent(m.group(1)), strip_inline(m.group(2))))
            i += 1
            continue

        # 마크다운 제목(### ...) → 굵은 한 줄 문단처럼 취급(평문화).
        if stripped.startswith("#"):
            flush_bullets()
            para.append(strip_inline(stripped.lstrip("#").strip()))
            i += 1
            continue

        # 일반 문단 줄.
        flush_bullets()
        para.append(strip_inline(stripped))
        i += 1

    flush_para()
    flush_bullets()
    return blocks
