"""한국 달력 보정 헬퍼 (T9 Phase D).

요구사항 0518: "대화 날짜: 1일, 8일, 15일, 22일, 29일 인데 한국달력기준 빨간날이면
뒤에 날중 가장 가까운 검정색 평일"

- 대상 날짜: 매월 1/8/15/22/29
- 빨간날 = 토요일/일요일 + 한국 공휴일
- 공휴일은 hardcoded 리스트로 (v0.3 에서 holiday 라이브러리 도입 검토)
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

# 한국 공휴일 하드코딩 (2026년). 매년 업데이트 필요.
# 매년 1월 1일 / 설/추석 / 광복절 / 개천절 / 한글날 / 어린이날 / 현충일 / 부처님오신날 등.
# 정확한 음력 환산은 v0.3 에서 'korean_lunar_calendar' 패키지 도입.
# TODO(2027+): 'holidays' 또는 'korean_lunar_calendar' 패키지로 교체.
KOREAN_HOLIDAYS_2026: set[date] = {
    date(2026, 1, 1),    # 신정
    date(2026, 2, 16),   # 설 (월)
    date(2026, 2, 17),
    date(2026, 2, 18),
    date(2026, 3, 1),    # 삼일절 (일) — 휴일 대체
    date(2026, 5, 5),    # 어린이날
    date(2026, 5, 24),   # 부처님오신날
    date(2026, 6, 6),    # 현충일 (토)
    date(2026, 8, 15),   # 광복절 (토)
    date(2026, 9, 24),   # 추석
    date(2026, 9, 25),
    date(2026, 9, 26),
    date(2026, 10, 3),   # 개천절 (토)
    date(2026, 10, 9),   # 한글날
    date(2026, 12, 25),  # 성탄절
}

# 대화 트리거 일자
TRIGGER_DAYS = (1, 8, 15, 22, 29)


def is_korean_holiday(d: date) -> bool:
    """주말 또는 한국 공휴일 여부."""
    if d.weekday() >= 5:  # 5=토, 6=일
        return True
    if d.year == 2026 and d in KOREAN_HOLIDAYS_2026:
        return True
    return False


def next_business_day(d: date) -> date:
    """d 가 평일이면 그대로, 빨간날이면 다음 평일."""
    cur = d
    while is_korean_holiday(cur):
        cur += timedelta(days=1)
    return cur


def adjusted_trigger_dates(year: int, month: int) -> list[date]:
    """해당 월의 1/8/15/22/29 빨간날 보정 결과."""
    out: list[date] = []
    for day in TRIGGER_DAYS:
        try:
            d = date(year, month, day)
        except ValueError:
            # 2월 29 등 존재하지 않는 날짜 skip
            continue
        out.append(next_business_day(d))
    return out


def is_trigger_today(today: date) -> bool:
    """오늘이 트리거 일자 (보정 후) 인지 판단."""
    adjusted = adjusted_trigger_dates(today.year, today.month)
    return today in adjusted
