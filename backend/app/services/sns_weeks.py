"""월중 주차(week_of_month) 산식 단일화.

게시물 게재일 → 월중 주차(1~5)는 **floor((day-1)/7)+1** 로 계산한다. 이 식이
SNS 라우터의 여러 SQL 집계와 ``sns_export._week_of_month`` (Python)에 각각
복제돼 드리프트 위험이 있었다. SQL 측은 이 모듈의 :func:`week_of_month_expr`
하나로 통일한다.

floor 가 중요하다: ``cast(Integer)`` 는 반올림하므로 floor 를 명시하지 않으면
예컨대 26일이 5주차로 잘못 분류된다(올바른 값은 4주차). Python 측
``sns_export._week_of_month`` 의 ``((day - 1) // 7) + 1`` 과 동일 결과를 보장한다.
"""
from __future__ import annotations

from sqlalchemy import Integer, func


def week_of_month_expr(date_col):
    """``date_col`` (날짜/타임스탬프 컬럼) → 월중 주차(1~5) SQLAlchemy 표현식.

    포맷: ``floor((extract(day) - 1) / 7) + 1`` — ``.label("week_number")`` 부여.
    sns_export._week_of_month (Python floor) 와 동일 산식.
    """
    return (
        func.floor((func.extract("day", date_col) - 1) / 7).cast(Integer) + 1
    ).label("week_number")
