"""관리문서(구글시트/xlsx) → 월별 배포 레코드 파싱.

관리문서의 두 시트가 보고서 '운영 상세' 표의 원천이다(라이브 probe로 컬럼 확정):

- ``26_중국OTA``(중화권): 한 시트에 연중 데이터가 **월 섹션**으로 쌓여 있다.
  섹션 헤더는 B열 "2026년 N월 OTA 체험단 …". 데이터 컬럼(헤더는 섹션 다음 행):
  B=Media(플랫폼: 따종디엔핑/마펑워/씨트립, 그룹 첫행에만 채워짐) · E=KOC(계정명)
  · F=계정URL · G=팔로워수 · J=진행제품 · O=포스팅일자 · P=포스팅URL · Q=좋아요
  · R=즐겨찾기(보고서 '저장') · S=댓글. (H=단가는 "공개금지" → 보고서 제외.)
- ``26_북미체험단``(북미): 월 섹션 헤더 B열 "2026년 N월 북미 체험단 …". 컬럼:
  C=Media(ins/TK/tiktok) · D=KOC(계정명) · E=URL · F=팔로워수 · H=진행제품
  · M=포스팅일자 · N=포스팅URL · O=노출수 · P=좋아요 · Q=댓글 · R=공유 · S=즐겨찾기.

행(rows) 추상화(list[list]) 위에서 동작하므로 xlsx(openpyxl)·Google Sheets API
(values) 어느 소스든 같은 파서를 쓴다. 컬럼 위치가 시트에서 바뀌면 헤더 탐지로
재정렬하는 것은 후속 — 1차는 확정된 고정 인덱스 + 헤더 검증으로 안전하게 간다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# 시트 탭 이름(관리문서 고정). 시트 구조가 바뀌면 여기만 갱신.
SHEET_CHINA = "26_중국OTA"
SHEET_NA = "26_북미체험단"

# 월 섹션 헤더 패턴: "2026년 5월 OTA 체험단 …" / "2026년 5월 북미 체험단 …"
_SECTION_RE = re.compile(r"(\d{4})\s*년\s*(\d{1,2})\s*월")

# 북미 Media 약어 → 보고서 플랫폼 표기.
_NA_PLATFORM = {
    "ins": "인스타그램",
    "instagram": "인스타그램",
    "tk": "틱톡",
    "tiktok": "틱톡",
    "yt": "유튜브",
    "youtube": "유튜브",
}


@dataclass
class DistRecord:
    """배포 게시물 1건(보고서 운영 상세 표의 한 행)."""

    platform: str = ""          # 플랫폼(마펑워/씨트립/따종디엔핑/인스타그램/틱톡)
    account: str = ""           # 계정명(KOC)
    followers: int | None = None
    product: str = ""           # 진행 제품
    post_date: str = ""         # 배포 날짜(YYYY-MM-DD)
    url: str = ""               # 배포 링크
    likes: int | None = None
    saves: int | None = None    # 중화권 즐겨찾기 / (북미는 별도)
    comments: int | None = None
    # 북미 전용
    impressions: int | None = None  # 노출수
    shares: int | None = None       # 공유
    favorites: int | None = None    # 즐겨찾기
    region: str = ""            # "china" | "na"


@dataclass
class MonthSection:
    """한 월 섹션(헤더 + 그 아래 배포 레코드들)."""

    year: int
    month: int
    products: str = ""          # 섹션 헤더에 적힌 진행 제품 문구
    records: list[DistRecord] = field(default_factory=list)


def _to_int(v) -> int | None:
    """숫자/문자 셀을 int로(쉼표·소수점·공백 허용, 빈값/"/"/"-"는 None)."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return int(v)
    s = str(v).strip().replace(",", "")
    if s in ("", "/", "-", "·"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def _to_date(v) -> str:
    """포스팅 일자 셀 → 'YYYY-MM-DD'(파싱 실패 시 원문 문자열)."""
    if v is None:
        return ""
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d")
    s = str(v).strip()
    if not s:
        return ""
    # "2026-05-20 00:00" / "2026.5.20" 등 흔한 형식 처리
    m = re.search(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})", s)
    if m:
        y, mo, d = (int(g) for g in m.groups())
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return s


def _cell(row: list, idx: int):
    """0-based 인덱스 안전 접근(범위 밖이면 None)."""
    return row[idx] if 0 <= idx < len(row) else None


def _section_match(row: list) -> tuple[int, int, str] | None:
    """행이 월 섹션 헤더면 (year, month, 제품문구) 반환, 아니면 None.

    헤더는 보통 B열(인덱스 1)에 있으나, 안전하게 앞쪽 셀들을 훑는다.
    'OTA 체험단' / '북미 체험단' 문구가 있어야 데이터 섹션 헤더로 인정한다.
    """
    for idx in range(0, min(3, len(row))):
        v = _cell(row, idx)
        if not isinstance(v, str):
            continue
        m = _SECTION_RE.search(v)
        if m and ("체험단" in v or "OTA" in v):
            year, month = int(m.group(1)), int(m.group(2))
            # "제품 :" 뒤 문구를 제품으로
            product = ""
            if ":" in v:
                product = v.split(":", 1)[1].strip()
            return year, month, product
    return None


def _is_data_row(row: list, account_idx: int, url_idx: int) -> bool:
    """계정명 또는 포스팅 URL이 있으면 데이터 행으로 본다(헤더/빈행 제외)."""
    acct = _cell(row, account_idx)
    url = _cell(row, url_idx)
    has_acct = isinstance(acct, str) and acct.strip() and acct.strip() not in ("KOC",)
    has_url = isinstance(url, str) and "http" in url
    return bool(has_acct or has_url)


def parse_china(rows: list[list]) -> list[MonthSection]:
    """26_중국OTA 시트 행들 → 월 섹션 리스트. 플랫폼(B열)은 그룹 첫행에만
    있고 이후 병합으로 비므로 forward-fill 한다."""
    # 컬럼 인덱스(0-based): B=1 Media, E=4 KOC, G=6 팔로워, J=9 제품,
    # O=14 포스팅일자, P=15 URL, Q=16 좋아요, R=17 즐겨찾기, S=18 댓글
    PLAT, ACCT, FOLL, PROD, DATE, URL, LIKE, SAVE, CMT = 1, 4, 6, 9, 14, 15, 16, 17, 18
    sections: list[MonthSection] = []
    cur: MonthSection | None = None
    last_platform = ""
    for row in rows:
        sec = _section_match(row)
        if sec:
            cur = MonthSection(year=sec[0], month=sec[1], products=sec[2])
            sections.append(cur)
            last_platform = ""
            continue
        if cur is None:
            continue
        plat = _cell(row, PLAT)
        if isinstance(plat, str) and plat.strip():
            # "따종디엔핑  (10명)" → "따종디엔핑"
            last_platform = re.split(r"[\s(（]", plat.strip())[0]
        if not _is_data_row(row, ACCT, URL):
            continue
        cur.records.append(DistRecord(
            region="china",
            platform=last_platform,
            account=str(_cell(row, ACCT) or "").strip(),
            followers=_to_int(_cell(row, FOLL)),
            product=str(_cell(row, PROD) or "").strip(),
            post_date=_to_date(_cell(row, DATE)),
            url=str(_cell(row, URL) or "").strip(),
            likes=_to_int(_cell(row, LIKE)),
            saves=_to_int(_cell(row, SAVE)),
            comments=_to_int(_cell(row, CMT)),
        ))
    return sections


def parse_na(rows: list[list]) -> list[MonthSection]:
    """26_북미체험단 시트 행들 → 월 섹션 리스트."""
    # C=2 Media, D=3 KOC, F=5 팔로워, H=7 제품, M=12 포스팅일자, N=13 URL,
    # O=14 노출, P=15 좋아요, Q=16 댓글, R=17 공유, S=18 즐겨찾기
    PLAT, ACCT, FOLL, PROD, DATE, URL, IMP, LIKE, CMT, SHARE, FAV = 2, 3, 5, 7, 12, 13, 14, 15, 16, 17, 18
    sections: list[MonthSection] = []
    cur: MonthSection | None = None
    for row in rows:
        sec = _section_match(row)
        if sec:
            cur = MonthSection(year=sec[0], month=sec[1], products=sec[2])
            sections.append(cur)
            continue
        if cur is None:
            continue
        if not _is_data_row(row, ACCT, URL):
            continue
        raw_plat = str(_cell(row, PLAT) or "").strip().lower()
        platform = _NA_PLATFORM.get(raw_plat, str(_cell(row, PLAT) or "").strip())
        cur.records.append(DistRecord(
            region="na",
            platform=platform,
            account=str(_cell(row, ACCT) or "").strip(),
            followers=_to_int(_cell(row, FOLL)),
            product=str(_cell(row, PROD) or "").strip(),
            post_date=_to_date(_cell(row, DATE)),
            url=str(_cell(row, URL) or "").strip(),
            impressions=_to_int(_cell(row, IMP)),
            likes=_to_int(_cell(row, LIKE)),
            comments=_to_int(_cell(row, CMT)),
            shares=_to_int(_cell(row, SHARE)),
            favorites=_to_int(_cell(row, FAV)),
        ))
    return sections


def pick_month(sections: list[MonthSection], month: int, year: int | None = None) -> list[MonthSection]:
    """지정 월(선택적으로 연도)의 섹션만. 한 월에 제품별 복수 섹션이 있을 수 있다."""
    return [s for s in sections if s.month == month and (year is None or s.year == year)]
