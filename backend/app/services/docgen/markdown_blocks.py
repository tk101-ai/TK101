"""섹션 body(마크다운) → 구조 블록 파서. pptx/docx 빌더 공용.

LLM이 body에 넣는 문단/불릿/표/차트를 디자인 렌더링이 가능한 블록 목록으로 변환한다.
지원 블록:
- paragraph : 일반 문단(여러 줄)
- bullets   : 불릿 목록. items=[(level, text)] (들여쓰기/중첩 단계 보존)
- table     : 마크다운 표 → rows=[[cell, ...]]
- chart     : ```chart {json} ``` 펜스 → data={type, title, categories, series}
- layout    : ```layout {json} ``` 펜스 → data={layout, ...slots} (고품질 슬라이드 원형)

차트 JSON 예:
    {"type":"bar","title":"분기 매출","categories":["1Q","2Q"],
     "series":[{"name":"매출","values":[10,14]}]}

레이아웃 JSON 예(아카이브 원형 — 렌더는 pptx_layouts):
    {"layout":"kpi","title":"핵심 지표","items":[{"value":"40%","label":"성장률","caption":"전년比"}]}
    {"layout":"compare","title":"비교","columns":[{"heading":"기존","points":["..."]},{"heading":"제안","points":["..."]}]}
    {"layout":"timeline","title":"로드맵","milestones":[{"label":"1단계","title":"...","detail":"..."}]}
    {"layout":"steps","title":"절차","steps":[{"title":"...","detail":"..."}]}
    {"layout":"quote","text":"핵심 한 줄","attribution":"출처"}
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_BULLET_RE = re.compile(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$")
_CHART_FENCE_RE = re.compile(r"^```chart\s*$", re.IGNORECASE)
_LAYOUT_FENCE_RE = re.compile(r"^```layout\s*$", re.IGNORECASE)
_FENCE_END_RE = re.compile(r"^```\s*$")
# 굵게(**...**) 마크업 — 셀/제목 정리용. 렌더러는 평문만 쓰므로 기호 제거.
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")

_VALID_CHART_TYPES = {"bar", "column", "line", "pie"}
_VALID_LAYOUTS = {"kpi", "compare", "timeline", "steps", "quote"}

# 레이아웃별 슬롯 개수 상한(한 슬라이드에 과밀 방지).
_LAYOUT_CAPS = {"kpi": 4, "compare": 3, "timeline": 5, "steps": 6}


@dataclass
class Block:
    kind: str                            # paragraph | bullets | table | chart | layout
    lines: list[str] = field(default_factory=list)        # paragraph
    items: list[tuple[int, str]] = field(default_factory=list)  # bullets (level, text)
    rows: list[list[str]] = field(default_factory=list)   # table
    data: dict | None = None                              # chart | layout


def strip_inline(text: str) -> str:
    """인라인 마크다운 기호 제거(평문 렌더용). 굵게/기울임/코드 백틱 정리."""
    text = _BOLD_RE.sub(r"\1", text)
    text = text.replace("`", "")
    return text.strip()


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


def _clean_list(values, *, fields: tuple[str, ...], required: str, cap: int) -> list[dict]:
    """객체 리스트 정규화 — required 필드가 빈 항목은 버리고, fields 만 평문화해 cap 까지."""
    out: list[dict] = []
    for v in values or []:
        if not isinstance(v, dict):
            continue
        item = {f: strip_inline(str(v.get(f) or "")) for f in fields}
        if not item.get(required):
            continue
        out.append(item)
        if len(out) >= cap:
            break
    return out


def _parse_layout(payload: str) -> dict | None:
    """레이아웃 펜스 본문(JSON) → 정규화 dict. 형식/내용 불량이면 None(렌더 건너뜀).

    렌더러(pptx_layouts)가 신뢰할 수 있도록 여기서 타입·슬롯·최소개수를 강제한다.
    """
    try:
        raw = json.loads(payload)
    except (json.JSONDecodeError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("layout") or "").lower().strip()
    if kind not in _VALID_LAYOUTS:
        return None
    title = strip_inline(str(raw.get("title") or ""))

    if kind == "kpi":
        items = _clean_list(raw.get("items"), fields=("value", "label", "caption"),
                            required="value", cap=_LAYOUT_CAPS["kpi"])
        if not items:
            return None
        return {"layout": "kpi", "title": title, "items": items}

    if kind == "compare":
        cols: list[dict] = []
        for c in raw.get("columns") or []:
            if not isinstance(c, dict):
                continue
            heading = strip_inline(str(c.get("heading") or ""))
            points = [strip_inline(str(p)) for p in (c.get("points") or []) if str(p).strip()]
            if heading or points:
                cols.append({"heading": heading, "points": points[:6]})
            if len(cols) >= _LAYOUT_CAPS["compare"]:
                break
        if len(cols) < 2:
            return None
        return {"layout": "compare", "title": title, "columns": cols}

    if kind == "timeline":
        ms = _clean_list(raw.get("milestones"), fields=("label", "title", "detail"),
                        required="title", cap=_LAYOUT_CAPS["timeline"])
        if len(ms) < 2:
            return None
        return {"layout": "timeline", "title": title, "milestones": ms}

    if kind == "steps":
        steps = _clean_list(raw.get("steps"), fields=("title", "detail"),
                           required="title", cap=_LAYOUT_CAPS["steps"])
        if len(steps) < 2:
            return None
        return {"layout": "steps", "title": title, "steps": steps}

    if kind == "quote":
        text = strip_inline(str(raw.get("text") or ""))
        if not text:
            return None
        return {"layout": "quote", "title": title, "text": text,
                "attribution": strip_inline(str(raw.get("attribution") or ""))}

    return None


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

        # 차트/레이아웃 펜스(같은 수집 로직, 파서만 다름).
        is_chart = _CHART_FENCE_RE.match(stripped)
        is_layout = _LAYOUT_FENCE_RE.match(stripped)
        if is_chart or is_layout:
            flush_para()
            flush_bullets()
            payload: list[str] = []
            i += 1
            while i < n and not _FENCE_END_RE.match(lines[i].strip()):
                payload.append(lines[i])
                i += 1
            i += 1  # 닫는 ``` 소비.
            joined = "\n".join(payload)
            if is_chart:
                data = _parse_chart(joined)
                if data:
                    blocks.append(Block(kind="chart", data=data))
            else:
                data = _parse_layout(joined)
                if data:
                    blocks.append(Block(kind="layout", data=data))
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
