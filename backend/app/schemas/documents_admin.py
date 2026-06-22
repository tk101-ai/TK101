"""관리자 전용 문서 사용량(토큰/비용) 집계 스키마 (PR-E #1).

form_jobs 단일 테이블을 kind(fill/generate) 일반화 후 집계해 관리자 패널에 노출한다.
"""
from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel

GroupBy = Literal["day", "user", "kind"]
KindFilter = Literal["fill", "generate", "all"]


class UsageRow(BaseModel):
    """집계 1행 — group_by 기준 버킷 + 합계."""

    bucket: str          # day: 'YYYY-MM-DD', user: 표시명, kind: 'fill'/'generate'
    kind: str | None     # group_by != 'kind' 면 None(여러 종류 합산 가능)
    job_count: int
    tokens_in: int
    tokens_out: int
    cost_usd: float


class UsageTotals(BaseModel):
    """기간 전체 합계."""

    job_count: int
    tokens_in: int
    tokens_out: int
    cost_usd: float


class UsageResponse(BaseModel):
    group_by: GroupBy
    start: date
    end: date
    rows: list[UsageRow]
    totals: UsageTotals
