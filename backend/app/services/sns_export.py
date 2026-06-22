"""SNS 데이터 → .xlsx 내보내기 헬퍼 (1단계).

각 함수는 행(row) 리스트를 받아 openpyxl ``Workbook`` 을 만들고 그 바이트(io.BytesIO)를
돌려준다. DB 접근은 일절 하지 않는다 — 라우터가 기존 쿼리로 행을 만들어 넘겨준다.

다중 클라이언트 안전:
    모든 시트는 계정(채널) 단위로 행을 돌며, 브랜드(client)/플랫폼/어권/핸들을 식별
    컬럼으로 항상 포함한다. 서울시 등 특정 발주처/채널을 하드코딩하지 않는다 —
    계정 쿼리에 행이 추가되면 코드 변경 없이 그대로 내보내기에 반영된다.
"""
from __future__ import annotations

import io
from typing import Any, Iterable, Sequence

from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter

# 어권/플랫폼 코드 → 사람이 읽는 한글 라벨. 미지의 값은 원본 코드를 그대로 쓴다
# (새 어권/플랫폼이 추가돼도 깨지지 않도록 — 데이터 주도).
LANGUAGE_LABELS: dict[str, str] = {"en": "영문", "zh": "중간체", "ja": "일문"}
PLATFORM_LABELS: dict[str, str] = {
    "facebook": "페이스북",
    "instagram": "인스타그램",
    "twitter": "트위터",
    "youtube": "유튜브",
    "weibo": "웨이보",
}

_HEADER_FONT = Font(bold=True)
_TOTAL_FONT = Font(bold=True)


def _label(mapping: dict[str, str], value: Any) -> str:
    """코드를 한글 라벨로. 없으면 원본 문자열, None 이면 빈 칸."""
    if value is None:
        return ""
    return mapping.get(str(value), str(value))


def _identity_cells(row: Any) -> list[Any]:
    """[브랜드(client), 플랫폼, 어권, 핸들] — 모든 시트 공통 식별 컬럼."""
    return [
        getattr(row, "client", None) or "",
        _label(PLATFORM_LABELS, getattr(row, "platform", None)),
        _label(LANGUAGE_LABELS, getattr(row, "language", None)),
        getattr(row, "handle", None) or "",
    ]


def _autosize(ws: Any, headers: Sequence[str], sample_widths: Sequence[int] | None = None) -> None:
    """간단한 컬럼 너비 — 헤더 길이 기반(+여유). 한글은 폭이 넓어 1.6배 가중."""
    for idx, header in enumerate(headers, start=1):
        base = max(len(str(header)) * 1.6, 8)
        if sample_widths and idx - 1 < len(sample_widths):
            base = max(base, sample_widths[idx - 1])
        ws.column_dimensions[get_column_letter(idx)].width = min(base + 2, 60)


def _write_header(ws: Any, headers: Sequence[str]) -> None:
    ws.append(list(headers))
    for cell in ws[1]:
        cell.font = _HEADER_FONT


def _finalize(wb: Workbook) -> io.BytesIO:
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# 주차 컬럼 5개 + 합계. 콘텐츠 현황 시트가 쓴다.
_WEEK_HEADERS = ["1주차", "2주차", "3주차", "4주차", "5주차"]


def build_content_status_workbook(rows: Iterable[Any]) -> io.BytesIO:
    """콘텐츠 현황(주차별 게재건수) — 계정당 1행 + 맨 아래 전체 합계.

    행(row)은 ``WeeklyPostCountRow`` 류로 client/platform/language/handle 과
    week1..week5, total 속성을 갖는다(stats_weekly_posts 산출물).
    """
    headers = ["브랜드", "플랫폼", "어권", "핸들", *_WEEK_HEADERS, "합계"]
    wb = Workbook()
    ws = wb.active
    ws.title = "콘텐츠현황"
    _write_header(ws, headers)

    totals = [0, 0, 0, 0, 0]
    grand_total = 0
    for row in rows:
        weeks = [int(getattr(row, f"week{i}", 0) or 0) for i in range(1, 6)]
        total = int(getattr(row, "total", 0) or 0)
        for i in range(5):
            totals[i] += weeks[i]
        grand_total += total
        ws.append([*_identity_cells(row), *weeks, total])

    # 전체 합계 행.
    total_row_idx = ws.max_row + 1
    ws.append(["전체 합계", "", "", "", *totals, grand_total])
    for cell in ws[total_row_idx]:
        cell.font = _TOTAL_FONT

    _autosize(ws, headers)
    return _finalize(wb)


def build_snapshots_workbook(rows: Iterable[Any]) -> io.BytesIO:
    """주간 팔로워 — 계정당 1행, 1~5주차 팔로워 수.

    행(row)은 client/platform/language/handle 과 week1..week5(팔로워, None 가능)를 갖는다.
    """
    headers = ["브랜드", "플랫폼", "어권", "핸들", *_WEEK_HEADERS]
    wb = Workbook()
    ws = wb.active
    ws.title = "주간팔로워"
    _write_header(ws, headers)

    for row in rows:
        weeks = [getattr(row, f"week{i}", None) for i in range(1, 6)]
        # None(미입력)은 빈 칸으로 둔다.
        cells = ["" if w is None else int(w) for w in weeks]
        ws.append([*_identity_cells(row), *cells])

    _autosize(ws, headers)
    return _finalize(wb)


def build_posts_workbook(rows: Iterable[Any]) -> io.BytesIO:
    """게시물 목록 — 게시물당 1행. 계정 식별 컬럼 + 게시물 필드.

    행(row)은 client/platform/language/handle(계정) 과
    posted_at/title/content_type/producer/view_count/reach_count/comment_count/
    like_count/share_count/total_engagement/url(게시물) 속성을 갖는다.
    """
    headers = [
        "브랜드",
        "플랫폼",
        "어권",
        "핸들",
        "게재일",
        "제목",
        "형태",
        "제작",
        "조회수",
        "도달",
        "댓글",
        "좋아요",
        "공유",
        "토탈인게이지먼트",
        "링크",
    ]
    wb = Workbook()
    ws = wb.active
    ws.title = "게시물"
    _write_header(ws, headers)

    for row in rows:
        posted_at = getattr(row, "posted_at", None)
        ws.append(
            [
                *_identity_cells(row),
                "" if posted_at is None else str(posted_at),
                getattr(row, "title", None) or "",
                getattr(row, "content_type", None) or "",
                getattr(row, "producer", None) or "",
                _num(getattr(row, "view_count", None)),
                _num(getattr(row, "reach_count", None)),
                _num(getattr(row, "comment_count", None)),
                _num(getattr(row, "like_count", None)),
                _num(getattr(row, "share_count", None)),
                _num(getattr(row, "total_engagement", None)),
                getattr(row, "url", None) or "",
            ]
        )

    _autosize(ws, headers)
    return _finalize(wb)


def _num(value: Any) -> Any:
    """숫자 칸 — None 이면 빈 칸, 아니면 정수로."""
    if value is None:
        return ""
    try:
        return int(value)
    except (TypeError, ValueError):
        return value
