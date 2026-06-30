"""필터링된 배포 레코드 → 보고서 표 행 + 운영 요약 집계.

선택 규칙(실제 5월 보고서 역설계로 확정): **배포완료(포스팅 일자가 있는) 레코드만**
보고서에 싣는다. 미배포("대리 배포 섭외"/날짜·지표 없음) 행은 제외.

합계 산식(실제 보고서 역산 검증):
- 중화권: 합계 = 좋아요 + 저장 + 댓글 (총인터랙션 동일식)
- 북미: 합계 = 좋아요 + 댓글 + 공유 + 즐겨찾기 (노출 제외)

진행제품·배포수량·배포데이터는 데이터에서 결정적으로 계산된다(라이브 검증:
중화권 좋아요1,184/댓글57/즐겨찾기434/총1,675 정확 일치). 홍보방향·진행이슈는
시트에 없어 AI 초안 대상(narrative 모듈).
"""
from __future__ import annotations

from .sheet_parser import DistRecord, MonthSection

# 운영 상세 표 헤더(템플릿과 동일 순서) ----------------------------------------
CHINA_DETAIL_HEADERS = [
    "No.", "플랫폼", "계정명", "팔로워 수", "진행 제품", "배포 날짜",
    "좋아요", "저장", "댓글", "합계", "배포 링크",
]
NA_DETAIL_HEADERS = [
    "No.", "플랫폼", "계정명", "팔로워 수", "진행 제품", "배포 날짜",
    "노출수", "좋아요", "댓글", "공유", "즐겨찾기", "합계", "배포 링크",
]

# 중화권 운영 상세 슬라이드 분할: OTA(마펑워·씨트립) vs 따종디엔핑
CHINA_OTA_PLATFORMS = ("마펑워", "씨트립")
CHINA_DZDP_PLATFORMS = ("따종디엔핑",)

_LINK_LABEL = "바로가기"


def _n(v) -> int:
    return int(v) if v else 0


def _fmt(v) -> str:
    """숫자 천단위 콤마, None은 빈칸."""
    return f"{int(v):,}" if isinstance(v, (int, float)) and v is not None else ""


def distributed(records: list[DistRecord]) -> list[DistRecord]:
    """배포완료(포스팅 일자가 있는) 레코드만."""
    return [r for r in records if r.post_date]


def flatten(sections: list[MonthSection]) -> list[DistRecord]:
    return [r for s in sections for r in s.records]


def products_label(sections: list[MonthSection]) -> str:
    """섹션들의 진행제품 문구를 ' / '로 결합(중복 제거, 순서 유지)."""
    seen: list[str] = []
    for s in sections:
        p = (s.products or "").strip()
        if p and p not in seen:
            seen.append(p)
    return " / ".join(seen)


def china_detail_rows(records: list[DistRecord], platforms: tuple[str, ...]) -> list[list]:
    """중화권 운영 상세 표 행들(헤더 제외). 진행제품은 직전 행과 다를 때만 표기."""
    rows: list[list] = []
    prev_prod = None
    n = 0
    for r in records:
        if r.platform not in platforms:
            continue
        n += 1
        total = _n(r.likes) + _n(r.saves) + _n(r.comments)
        prod = r.product if r.product != prev_prod else ""
        prev_prod = r.product
        rows.append([
            str(n), r.platform, r.account, _fmt(r.followers), prod, r.post_date,
            _fmt(r.likes), _fmt(r.saves), _fmt(r.comments), _fmt(total),
            (_LINK_LABEL, r.url),
        ])
    return rows


def na_detail_rows(records: list[DistRecord]) -> list[list]:
    """북미 운영 상세 표 행들(헤더 제외)."""
    rows: list[list] = []
    prev_prod = None
    n = 0
    for r in records:
        n += 1
        total = _n(r.likes) + _n(r.comments) + _n(r.shares) + _n(r.favorites)
        prod = r.product if r.product != prev_prod else ""
        prev_prod = r.product
        rows.append([
            str(n), r.platform, r.account, _fmt(r.followers), prod, r.post_date,
            _fmt(r.impressions), _fmt(r.likes), _fmt(r.comments), _fmt(r.shares),
            _fmt(r.favorites), _fmt(total), (_LINK_LABEL, r.url),
        ])
    return rows


def _count_by_platform(records, platforms):
    return {p: sum(1 for r in records if r.platform == p) for p in platforms}


def china_summary(records: list[DistRecord], sections: list[MonthSection]) -> dict:
    """중화권 운영 요약(진행제품/배포수량/배포데이터). 홍보방향·이슈는 별도(AI)."""
    ota = sum(1 for r in records if r.platform in CHINA_OTA_PLATFORMS)
    dzdp = sum(1 for r in records if r.platform in CHINA_DZDP_PLATFORMS)
    likes = sum(_n(r.likes) for r in records)
    comments = sum(_n(r.comments) for r in records)
    saves = sum(_n(r.saves) for r in records)
    total = likes + comments + saves
    return {
        "진행 제품": products_label(sections),
        "배포 수량": f"1) OTA-마펑워&씨트립: {ota}건; 2) 따종디엔핑: {dzdp}건;",
        "배포 데이터": (
            f"1. 좋아요 수: {likes:,}건; 댓글 수: {comments:,}건; 즐겨찾기 수: {saves:,}건;\n"
            f"2. 총 인터랙션 수: {total:,}건"
        ),
    }


def na_summary(records: list[DistRecord], sections: list[MonthSection]) -> dict:
    """북미 운영 요약(진행제품/배포수량/배포데이터)."""
    insta = sum(1 for r in records if r.platform == "인스타그램")
    tiktok = sum(1 for r in records if r.platform == "틱톡")
    imp = sum(_n(r.impressions) for r in records)
    likes = sum(_n(r.likes) for r in records)
    comments = sum(_n(r.comments) for r in records)
    shares = sum(_n(r.shares) for r in records)
    favs = sum(_n(r.favorites) for r in records)
    total = likes + comments + shares + favs
    return {
        "진행 제품": products_label(sections),
        "배포 수량": f"1) 인스타그램: {insta}건; 2) 틱톡: {tiktok}건;",
        "배포 데이터": (
            f"1. 노출 수: {imp:,}회\n"
            f"2. 좋아요 수: {likes:,}건; 댓글 수: {comments:,}건; 공유 수: {shares:,}건; "
            f"즐겨찾기 수: {favs:,}건;\n총 인터랙션 수: {total:,}건"
        ),
    }
