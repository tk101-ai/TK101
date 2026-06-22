"""구조화 섹션 → 디자인된 .pptx 바이트.

빈 흰 슬라이드에 글만 찍던 기존 렌더를 교체. 16:9 + 브랜드 테마(theme.py)로
표지·목차·섹션 슬라이드(컬러 제목·불릿)·스타일 표·네이티브 차트·푸터를 구성한다.
body 의 불릿/표/차트는 markdown_blocks.parse_blocks 로 해석한다.

회사 .pptx 템플릿(settings.docgen_pptx_template)이 있으면 그 마스터를 베이스로 쓴다.
"""
from __future__ import annotations

import io
import logging
from datetime import date

from app.services.docgen.markdown_blocks import Block, parse_blocks
from app.services.docgen.theme import Theme, get_theme

logger = logging.getLogger(__name__)

# 슬라이드 한 장에 들어갈 본문 텍스트 줄 수 상한(넘으면 다음 장으로 분할).
_MAX_TEXT_LINES = 9
# 표 한 장 최대 행 수(헤더 포함). 넘으면 분할.
_MAX_TABLE_ROWS = 12
_BULLET_GLYPHS = ("•", "–", "·", "·", "·")


def _rgb(color: tuple[int, int, int]):
    from pptx.dml.color import RGBColor

    return RGBColor(*color)


def _blank_layout(prs):
    """플레이스홀더가 가장 적은(빈) 레이아웃 — 기본/커스텀 템플릿 모두 안전."""
    best, best_count = None, 999
    for lay in prs.slide_layouts:
        count = len(lay.placeholders)
        if count < best_count:
            best, best_count = lay, count
    return best or prs.slide_layouts[0]


def _add_rect(slide, x, y, w, h, color, line_color=None):
    from pptx.enum.shapes import MSO_SHAPE

    shape = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, x, y, w, h)
    shape.fill.solid()
    shape.fill.fore_color.rgb = _rgb(color)
    if line_color is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = _rgb(line_color)
    shape.shadow.inherit = False
    return shape


def _add_text(slide, x, y, w, h, text, *, size, color, font, bold=False,
              align=None, anchor=None):
    from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
    from pptx.util import Pt

    box = slide.shapes.add_textbox(x, y, w, h)
    tf = box.text_frame
    tf.word_wrap = True
    if anchor is not None:
        tf.vertical_anchor = {"top": MSO_ANCHOR.TOP, "middle": MSO_ANCHOR.MIDDLE,
                              "bottom": MSO_ANCHOR.BOTTOM}[anchor]
    p = tf.paragraphs[0]
    if align is not None:
        p.alignment = {"left": PP_ALIGN.LEFT, "center": PP_ALIGN.CENTER,
                       "right": PP_ALIGN.RIGHT}[align]
    run = p.add_run()
    run.text = text
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.name = font
    run.font.color.rgb = _rgb(color)
    return box


def _slide_dims(prs):
    return prs.slide_width, prs.slide_height


# --- 슬라이드 구성요소 ------------------------------------------------------


def _add_footer(slide, prs, theme: Theme, page_no: int) -> None:
    from pptx.util import Inches, Pt

    sw, sh = _slide_dims(prs)
    # 옅은 구분선.
    _add_rect(slide, Inches(0.6), sh - Inches(0.62), sw - Inches(1.2), Pt(0.75),
              theme.light_bg)
    if theme.footer_text:
        _add_text(slide, Inches(0.6), sh - Inches(0.6), Inches(6), Inches(0.35),
                  theme.footer_text, size=9, color=theme.muted, font=theme.body_font,
                  align="left", anchor="middle")
    _add_text(slide, sw - Inches(1.6), sh - Inches(0.6), Inches(1.0), Inches(0.35),
              str(page_no), size=9, color=theme.muted, font=theme.body_font,
              align="right", anchor="middle")


def _add_title_bar(slide, prs, theme: Theme, heading: str, continued: bool) -> None:
    """본문 슬라이드 상단 제목 + 액센트 밑줄."""
    from pptx.util import Inches, Pt

    sw, _ = _slide_dims(prs)
    text = heading or " "
    if continued:
        text += "  (계속)"
    _add_text(slide, Inches(0.6), Inches(0.42), sw - Inches(1.2), Inches(0.8),
              text, size=26, color=theme.primary, font=theme.heading_font,
              bold=True, align="left", anchor="middle")
    _add_rect(slide, Inches(0.62), Inches(1.28), Inches(1.9), Pt(3.5), theme.accent)


def _cover_slide(prs, theme: Theme, title: str, subtitle: str) -> None:
    from pptx.util import Inches, Pt

    slide = prs.slides.add_slide(_blank_layout(prs))
    sw, sh = _slide_dims(prs)
    # 풀블리드 배경 + 액센트 사이드바.
    _add_rect(slide, 0, 0, sw, sh, theme.primary)
    _add_rect(slide, 0, sh - Inches(2.0), sw, Inches(0.12), theme.accent)
    _add_rect(slide, Inches(0.0), Inches(2.6), Inches(0.18), Inches(2.0), theme.accent)
    # 로고(있으면 좌상단).
    if theme.logo_path:
        try:
            slide.shapes.add_picture(theme.logo_path, Inches(0.6), Inches(0.55),
                                     height=Inches(0.7))
        except Exception:  # noqa: BLE001 - 로고 깨져도 표지는 나와야 함
            pass
    _add_text(slide, Inches(0.7), Inches(2.5), sw - Inches(1.4), Inches(2.2),
              title or "문서", size=40, color=theme.white, font=theme.heading_font,
              bold=True, align="left", anchor="middle")
    # 진한 배경 위라 부제/푸터는 흐린 흰색으로.
    _cover_sub = (0xD7, 0xDE, 0xEA)
    if subtitle:
        _add_text(slide, Inches(0.72), Inches(4.7), sw - Inches(1.4), Inches(0.6),
                  subtitle, size=16, color=_cover_sub,
                  font=theme.body_font, align="left")
    if theme.footer_text:
        _add_text(slide, Inches(0.72), sh - Inches(0.95), sw - Inches(1.4),
                  Inches(0.5), theme.footer_text, size=12,
                  color=_cover_sub, font=theme.body_font,
                  align="left", anchor="middle")


def _agenda_slide(prs, theme: Theme, headings: list[str], page_no: int) -> None:
    from pptx.util import Inches, Pt

    slide = prs.slides.add_slide(_blank_layout(prs))
    _add_title_bar(slide, prs, theme, "목차", False)
    top = Inches(1.7)
    for idx, h in enumerate(headings, 1):
        y = top + Inches(0.62) * (idx - 1)
        # 번호 배지.
        badge = _add_rect(slide, Inches(0.7), y, Inches(0.5), Inches(0.45), theme.accent)
        tf = badge.text_frame
        tf.word_wrap = False
        from pptx.enum.text import PP_ALIGN
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        run = p.add_run()
        run.text = str(idx)
        run.font.size = Pt(14)
        run.font.bold = True
        run.font.name = theme.heading_font
        run.font.color.rgb = _rgb(theme.white)
        _add_text(slide, Inches(1.4), y - Inches(0.02), Inches(11.0), Inches(0.5),
                  h, size=16, color=theme.text, font=theme.body_font, anchor="middle")
    _add_footer(slide, prs, theme, page_no)


def _text_lines_from_blocks(blocks: list[Block]) -> list[tuple[int, str, bool]]:
    """문단/불릿 블록을 (level, text, is_bullet) 줄 목록으로 평탄화."""
    lines: list[tuple[int, str, bool]] = []
    for b in blocks:
        if b.kind == "paragraph":
            for ln in b.lines:
                if ln.strip():
                    lines.append((0, ln.strip(), False))
        elif b.kind == "bullets":
            for level, text in b.items:
                if text.strip():
                    lines.append((level, text.strip(), True))
    return lines


def _add_text_slide(prs, theme: Theme, heading: str, lines, continued: bool,
                    page_no: int) -> None:
    from pptx.enum.text import MSO_ANCHOR
    from pptx.util import Inches, Pt

    slide = prs.slides.add_slide(_blank_layout(prs))
    _add_title_bar(slide, prs, theme, heading, continued)
    sw, _ = _slide_dims(prs)
    box = slide.shapes.add_textbox(Inches(0.7), Inches(1.6), sw - Inches(1.4),
                                   Inches(4.9))
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.TOP
    for idx, (level, text, is_bullet) in enumerate(lines):
        p = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
        p.space_after = Pt(8)
        p.line_spacing = 1.15
        run = p.add_run()
        if is_bullet:
            glyph = _BULLET_GLYPHS[min(level, len(_BULLET_GLYPHS) - 1)]
            run.text = ("    " * level) + f"{glyph}  " + text
            run.font.size = Pt(17 if level == 0 else 15)
            run.font.color.rgb = _rgb(theme.text)
        else:
            run.text = text
            run.font.size = Pt(16)
            run.font.color.rgb = _rgb(theme.text)
        run.font.name = theme.body_font
    _add_footer(slide, prs, theme, page_no)


def _add_table_slide(prs, theme: Theme, heading: str, rows: list[list[str]],
                     continued: bool, page_no: int) -> None:
    from pptx.enum.text import PP_ALIGN
    from pptx.util import Inches, Pt

    if not rows:
        return
    slide = prs.slides.add_slide(_blank_layout(prs))
    _add_title_bar(slide, prs, theme, heading, continued)
    sw, _ = _slide_dims(prs)
    ncol = max(len(r) for r in rows)
    nrow = len(rows)
    left, top = Inches(0.7), Inches(1.7)
    width, height = sw - Inches(1.4), Inches(min(0.5 * nrow, 4.8))
    table = slide.shapes.add_table(nrow, ncol, left, top, width, height).table
    for i, r in enumerate(rows):
        is_header = i == 0
        for j in range(ncol):
            cell = table.cell(i, j)
            cell.text = r[j] if j < len(r) else ""
            cell.fill.solid()
            if is_header:
                cell.fill.fore_color.rgb = _rgb(theme.primary)
            elif i % 2 == 0:
                cell.fill.fore_color.rgb = _rgb(theme.table_stripe)
            else:
                cell.fill.fore_color.rgb = _rgb(theme.white)
            for para in cell.text_frame.paragraphs:
                para.alignment = PP_ALIGN.LEFT
                for run in para.runs:
                    run.font.size = Pt(12)
                    run.font.name = theme.body_font
                    run.font.bold = is_header
                    run.font.color.rgb = _rgb(theme.white if is_header else theme.text)
    _add_footer(slide, prs, theme, page_no)


def _chart_type(kind: str):
    from pptx.enum.chart import XL_CHART_TYPE

    return {
        "bar": XL_CHART_TYPE.BAR_CLUSTERED,
        "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
        "line": XL_CHART_TYPE.LINE_MARKERS,
        "pie": XL_CHART_TYPE.PIE,
    }.get(kind, XL_CHART_TYPE.COLUMN_CLUSTERED)


def _add_chart_slide(prs, theme: Theme, heading: str, data: dict, page_no: int) -> None:
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_LEGEND_POSITION
    from pptx.util import Inches

    slide = prs.slides.add_slide(_blank_layout(prs))
    title = data.get("title") or heading
    _add_title_bar(slide, prs, theme, title, False)
    sw, _ = _slide_dims(prs)
    # 잘못된 LLM 차트 스펙(다중 시리즈 pie·비숫자 값 등)이 python-pptx 내부에서
    # 예외를 던져 덱 전체 렌더가 500 나는 걸 막는다. 실패 시 해당 차트만 건너뛰고
    # 플레이스홀더 텍스트로 대체 — 나머지 슬라이드는 정상 렌더.
    try:
        chart_data = CategoryChartData()
        chart_data.categories = data["categories"]
        for s in data["series"]:
            chart_data.add_series(s["name"], s["values"])
        graphic = slide.shapes.add_chart(
            _chart_type(data["type"]), Inches(0.8), Inches(1.7),
            sw - Inches(1.6), Inches(4.7), chart_data,
        )
        chart = graphic.chart
        chart.has_title = False
        if len(data["series"]) > 1:
            chart.has_legend = True
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
        else:
            chart.has_legend = False
    except Exception:  # noqa: BLE001 - 차트 깨져도 덱은 나와야 함
        logger.warning("차트 렌더 실패 — 플레이스홀더로 대체: %s", title, exc_info=True)
        _add_text(slide, Inches(0.8), Inches(1.7), sw - Inches(1.6), Inches(4.7),
                  "[차트를 표시할 수 없습니다]", size=16, color=theme.text,
                  font=theme.body_font, align="left", anchor="middle")
    _add_footer(slide, prs, theme, page_no)


def _render_section(prs, theme: Theme, heading: str, blocks: list[Block],
                    counter: list[int]) -> None:
    """한 섹션 → 텍스트/표/차트 슬라이드. counter[0]=현재 페이지 번호(가변)."""
    pending_text: list[Block] = []
    first_text = True

    def flush_text(more_after: bool) -> None:
        nonlocal first_text
        lines = _text_lines_from_blocks(pending_text)
        pending_text.clear()
        if not lines:
            return
        # _MAX_TEXT_LINES 단위로 분할.
        for start in range(0, len(lines), _MAX_TEXT_LINES):
            chunk = lines[start:start + _MAX_TEXT_LINES]
            counter[0] += 1
            _add_text_slide(prs, theme, heading, chunk, not first_text, counter[0])
            first_text = False

    for b in blocks:
        if b.kind in ("paragraph", "bullets"):
            pending_text.append(b)
        elif b.kind == "table":
            flush_text(True)
            rows = b.rows
            for start in range(0, len(rows), _MAX_TABLE_ROWS):
                chunk = rows[start:start + _MAX_TABLE_ROWS]
                # 분할 시 헤더 반복.
                if start > 0 and rows:
                    chunk = [rows[0]] + chunk
                counter[0] += 1
                _add_table_slide(prs, theme, heading, chunk, start > 0, counter[0])
        elif b.kind == "chart":
            flush_text(True)
            counter[0] += 1
            _add_chart_slide(prs, theme, heading, b.data, counter[0])
    flush_text(False)
    # 본문이 완전히 비었던 섹션도 제목 슬라이드 한 장 남긴다.
    if first_text and not any(b.kind in ("table", "chart") for b in blocks):
        counter[0] += 1
        _add_text_slide(prs, theme, heading, [], False, counter[0])


def build_pptx(title: str, sections: list[dict]) -> bytes:
    """title + sections([{heading, body}]) → 디자인된 .pptx 바이트."""
    from pptx import Presentation
    from pptx.util import Inches

    theme = get_theme()
    prs = Presentation(theme.pptx_template) if theme.pptx_template else Presentation()
    # 16:9. (커스텀 템플릿이면 템플릿 크기를 존중해 덮어쓰지 않음.)
    if not theme.pptx_template:
        prs.slide_width = Inches(13.333)
        prs.slide_height = Inches(7.5)

    today = date.today().strftime("%Y.%m.%d")
    subtitle = f"{today}"
    _cover_slide(prs, theme, title, subtitle)

    headings = [(s.get("heading") or "").strip() for s in sections]
    headings = [h for h in headings if h]
    counter = [1]  # 표지=1.
    if len(headings) >= 2:
        counter[0] += 1
        _agenda_slide(prs, theme, headings, counter[0])

    for s in sections:
        heading = (s.get("heading") or "").strip()
        body = (s.get("body") or "").strip()
        _render_section(prs, theme, heading, parse_blocks(body), counter)

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
