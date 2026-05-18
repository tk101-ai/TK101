"""신사업유통 T9 Phase B-2 전용 스키마.

별도 파일에 둔 이유:
- 기존 ``schemas/distribution.py`` 는 페르소나/시나리오/단일 generate 흐름에 묶여 있어
  수정 시 회귀 위험이 큼.
- B-2 는 "4페어 동시 주간 생성" 신규 흐름이므로 격리하여 라우터에서 추가 import 만으로 사용.

엔드포인트 매핑(예정):
- POST /api/distribution/weekly/generate → GenerateWeeklyRequest / GenerateWeeklyResult
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class GenerateWeeklyRequest(BaseModel):
    """4페어 주간 생성 요청.

    scenario_names 가 비어있으면 ``generation_service`` 의 기본 시나리오
    (weekly_settlement + product_request) 가 사용됨.
    company_label 은 ``distribution_weekly_summary.company_label`` 과 매칭.
    """

    scenario_names: list[str] = Field(
        default_factory=list,
        description="시나리오 name 화이트리스트. 비어있으면 기본값 사용.",
    )
    company_label: str = Field(
        default="래더엑스",
        min_length=1,
        max_length=100,
        description="distribution_weekly_summary.company_label 매칭값",
    )


class GenerateWeeklyResult(BaseModel):
    """4페어 주간 생성 결과 요약."""

    sessions_created: list[UUID] = Field(
        default_factory=list,
        description="새로 생성된 distribution_sessions.id 목록 (status='pending')",
    )
    skipped: list[str] = Field(
        default_factory=list,
        description="생성 건너뛴 항목 ('KR-A2: credentials missing' 형태)",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="생성 실패 항목 ('KR-A3 / weekly_settlement: <err>' 형태)",
    )
