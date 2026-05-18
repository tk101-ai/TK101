"""신사업유통 분석 페이지 Pydantic 응답 스키마 (T9 Phase E-4).

라우터: ``app/routers/distribution_analytics.py``
서비스: ``app/services/distribution/analytics_service.py``

직렬화 정책:
- 금액(``total_cost_usd``)은 ``Decimal`` 으로 두어 정밀도 보존 (프론트는 string 으로 받음).
- 카운트는 ``int``.
- ``sent_at`` 은 nullable (queued 상태 메시지는 NULL).
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class CostByDayItem(BaseModel):
    """일별 Claude 비용 1행."""

    date: date
    total_cost_usd: Decimal
    session_count: int


class CostByPersonaItem(BaseModel):
    """페르소나별 Claude 비용 1행."""

    persona_id: UUID
    account_label: str
    total_cost_usd: Decimal
    session_count: int


class SendFailureItem(BaseModel):
    """송신 실패 원인 분류 1행.

    ``error_code`` NULL 은 서비스에서 "UNKNOWN" 으로 변환됨.
    """

    error_code: str
    count: int
    last_attempted_at: datetime


class MessageSearchItem(BaseModel):
    """메시지 검색 결과 1행.

    ``content`` 는 서비스에서 ``edited_content`` 우선 폴백 처리됨.
    """

    message_id: UUID
    session_id: UUID
    scenario_name: str
    sender_account_label: str
    content: str
    sent_at: datetime | None
    status: str
