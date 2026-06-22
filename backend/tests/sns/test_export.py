"""sns_export 워크북 빌더 단위 테스트 (DB 미접근, openpyxl 라운드트립)."""
from datetime import date
from types import SimpleNamespace

from openpyxl import load_workbook

from app.services.sns_export import (
    build_content_status_workbook,
    build_posts_workbook,
    build_snapshots_workbook,
)


def _load(buf):
    return load_workbook(buf).active


def test_content_status_has_identity_columns_and_total_row():
    rows = [
        SimpleNamespace(
            client="서울시", platform="facebook", language="en", handle="seoul.en",
            week1=2, week2=1, week3=0, week4=3, week5=0, total=6,
        ),
        SimpleNamespace(
            client="신세계", platform="instagram", language="zh", handle="ss.zh",
            week1=1, week2=1, week3=1, week4=1, week5=1, total=5,
        ),
    ]
    ws = _load(build_content_status_workbook(rows))
    assert [c.value for c in ws[1]] == [
        "브랜드", "플랫폼", "어권", "핸들",
        "1주차", "2주차", "3주차", "4주차", "5주차", "합계",
    ]
    # 코드값이 아니라 한글 라벨로 내보낸다 + 브랜드 컬럼이 데이터 주도(하드코딩 아님).
    assert ws["A2"].value == "서울시"
    assert ws["A3"].value == "신세계"
    assert ws["B2"].value == "페이스북"
    assert ws["C2"].value == "영문"
    # 전체 합계 행.
    last = ws[ws.max_row]
    assert last[0].value == "전체 합계"
    assert last[9].value == 11  # 6 + 5


def test_snapshots_blank_for_missing_weeks():
    rows = [
        SimpleNamespace(
            client=None, platform="youtube", language="ja", handle="yt.ja",
            week1=100, week2=None, week3=120, week4=None, week5=None,
        )
    ]
    ws = _load(build_snapshots_workbook(rows))
    assert ws.title == "주간팔로워"
    assert [c.value for c in ws[1]] == [
        "브랜드", "플랫폼", "어권", "핸들",
        "1주차", "2주차", "3주차", "4주차", "5주차",
    ]
    assert ws["E2"].value == 100
    assert ws["F2"].value in (None, "")  # 미입력 주차는 빈 칸


def test_posts_columns_and_date_stringified():
    rows = [
        SimpleNamespace(
            client="서울시", platform="facebook", language="en", handle="seoul.en",
            posted_at=date(2026, 4, 3), title="제목", content_type="video",
            producer="TK제작", view_count=500, reach_count=None, comment_count=2,
            like_count=10, share_count=1, total_engagement=13, url="https://x",
        )
    ]
    ws = _load(build_posts_workbook(rows))
    assert [c.value for c in ws[1]] == [
        "브랜드", "플랫폼", "어권", "핸들", "게재일", "제목", "형태", "제작",
        "조회수", "도달", "댓글", "좋아요", "공유", "토탈인게이지먼트", "링크",
    ]
    assert ws["E2"].value == "2026-04-03"
    assert ws["I2"].value == 500
    assert ws["J2"].value in (None, "")  # 도달 None
    assert ws["O2"].value == "https://x"


def test_unknown_platform_falls_back_to_raw_value():
    # 새 플랫폼/어권이 추가돼도 깨지지 않고 원본 코드를 그대로 쓴다.
    rows = [
        SimpleNamespace(
            client="X", platform="tiktok", language="ko", handle="h",
            week1=0, week2=0, week3=0, week4=0, week5=0, total=0,
        )
    ]
    ws = _load(build_content_status_workbook(rows))
    assert ws["B2"].value == "tiktok"
    assert ws["C2"].value == "ko"
