"""신사업유통 분석 페이지 집계 서비스 (T9 Phase E-4).

라우터(`distribution_analytics.py`)에서 호출되는 분석/검색 함수 모음.

대시보드 서비스(`dashboard_service.py`)와의 차이:
- 대시보드 = KPI 카드 + 추이/분포 (의사결정 시각화)
- 분석 = 비용 추세 / 송신 실패 원인 / 메시지 텍스트 검색 (운영·디버깅)

설계 원칙:
- 모든 함수는 ``AsyncSession`` + 옵션 기간(``from_date`` / ``to_date``)을 받는다.
- 기간 미지정 시 전체 데이터를 집계한다.
- Decimal 합계는 ``float`` 으로 직렬화 (Pydantic 응답 친화적).
- 검색은 대소문자 무관 ``ILIKE`` — ``content`` OR ``edited_content`` 매칭.
"""
from __future__ import annotations

import logging
from datetime import date as date_cls
from decimal import Decimal
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import (
    DistributionMessage,
    DistributionPersona,
    DistributionScenario,
    DistributionSendLog,
    DistributionSession,
)

logger = logging.getLogger(__name__)


# 세션 상태 6종 — 대시보드와 동일한 키 집합 사용 (0건도 포함).
SESSION_STATUS_KEYS: tuple[str, ...] = (
    "pending",
    "approved",
    "rejected",
    "sending",
    "sent",
    "failed",
)


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------


def _to_float(value: Decimal | float | int | None) -> float:
    """Decimal/None 안전 float 변환. NULL 합계는 0.0."""
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _to_int(value: int | None) -> int:
    if value is None:
        return 0
    return int(value)


def _apply_session_period_filter(
    stmt, from_date: date_cls | None, to_date: date_cls | None
):
    """``DistributionSession.generated_at`` 기준 기간 필터."""
    if from_date is not None:
        stmt = stmt.where(func.date(DistributionSession.generated_at) >= from_date)
    if to_date is not None:
        stmt = stmt.where(func.date(DistributionSession.generated_at) <= to_date)
    return stmt


def _apply_send_log_period_filter(
    stmt, from_date: date_cls | None, to_date: date_cls | None
):
    """``DistributionSendLog.attempted_at`` 기준 기간 필터."""
    if from_date is not None:
        stmt = stmt.where(func.date(DistributionSendLog.attempted_at) >= from_date)
    if to_date is not None:
        stmt = stmt.where(func.date(DistributionSendLog.attempted_at) <= to_date)
    return stmt


def _apply_message_period_filter(
    stmt, from_date: date_cls | None, to_date: date_cls | None
):
    """메시지 검색용 — ``sent_at`` 우선, NULL 이면 세션 ``generated_at`` 으로 폴백."""
    # 메시지 검색은 sent_at 이 없을 수도 있으므로(queued), 세션 generated_at 기준이 안전.
    if from_date is not None:
        stmt = stmt.where(func.date(DistributionSession.generated_at) >= from_date)
    if to_date is not None:
        stmt = stmt.where(func.date(DistributionSession.generated_at) <= to_date)
    return stmt


# ---------------------------------------------------------------------------
# 1) Claude 비용 — 일별
# ---------------------------------------------------------------------------


async def cost_by_day(
    db: AsyncSession,
    *,
    from_date: date_cls | None,
    to_date: date_cls | None,
) -> list[dict[str, Any]]:
    """일별 Claude 비용 합계.

    반환: ``[{date, total_cost_usd, session_count}]`` — ``date`` 오름차순.

    같은 날짜에 여러 세션이 있으면 ``llm_cost_usd`` 합계 + 세션 수.
    ``llm_cost_usd`` 가 NULL 인 세션도 ``session_count`` 에는 포함.
    """
    day_col = func.date(DistributionSession.generated_at).label("day")
    stmt = (
        select(
            day_col,
            func.coalesce(func.sum(DistributionSession.llm_cost_usd), 0).label(
                "total_cost"
            ),
            func.count(DistributionSession.id).label("session_count"),
        )
        .group_by(day_col)
        .order_by(day_col.asc())
    )
    stmt = _apply_session_period_filter(stmt, from_date, to_date)
    rows = (await db.execute(stmt)).all()

    return [
        {
            "date": row.day,
            "total_cost_usd": _to_float(row.total_cost),
            "session_count": _to_int(row.session_count),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# 2) Claude 비용 — 페르소나(sender) 별
# ---------------------------------------------------------------------------


async def cost_by_persona(
    db: AsyncSession,
    *,
    from_date: date_cls | None,
    to_date: date_cls | None,
) -> list[dict[str, Any]]:
    """페르소나(sender_persona)별 Claude 비용 합계.

    반환: ``[{persona_id, account_label, total_cost_usd, session_count}]``
    — ``total_cost_usd`` 내림차순.

    같은 페르소나가 발신한 모든 세션의 비용 합계.
    """
    stmt = (
        select(
            DistributionPersona.id.label("persona_id"),
            DistributionPersona.account_label.label("account_label"),
            func.coalesce(func.sum(DistributionSession.llm_cost_usd), 0).label(
                "total_cost"
            ),
            func.count(DistributionSession.id).label("session_count"),
        )
        .join(
            DistributionSession,
            DistributionSession.sender_persona_id == DistributionPersona.id,
        )
        .group_by(DistributionPersona.id, DistributionPersona.account_label)
        .order_by(
            func.coalesce(func.sum(DistributionSession.llm_cost_usd), 0).desc(),
            DistributionPersona.account_label.asc(),
        )
    )
    stmt = _apply_session_period_filter(stmt, from_date, to_date)
    rows = (await db.execute(stmt)).all()

    return [
        {
            "persona_id": row.persona_id,
            "account_label": row.account_label,
            "total_cost_usd": _to_float(row.total_cost),
            "session_count": _to_int(row.session_count),
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# 3) 송신 실패 원인 분류
# ---------------------------------------------------------------------------


async def send_failure_breakdown(
    db: AsyncSession,
    *,
    from_date: date_cls | None,
    to_date: date_cls | None,
) -> list[dict[str, Any]]:
    """송신 실패 원인 분류.

    반환: ``[{error_code, count, last_attempted_at}]`` — ``count`` 내림차순.

    ``success=False`` 행만 카운트 (success NULL = 시도 중은 제외).
    ``error_code`` NULL 행은 "UNKNOWN" 으로 묶음.
    """
    error_code_col = func.coalesce(
        DistributionSendLog.error_code, "UNKNOWN"
    ).label("error_code")
    stmt = (
        select(
            error_code_col,
            func.count(DistributionSendLog.id).label("count"),
            func.max(DistributionSendLog.attempted_at).label("last_attempted_at"),
        )
        .where(DistributionSendLog.success.is_(False))
        .group_by(error_code_col)
        .order_by(func.count(DistributionSendLog.id).desc(), error_code_col.asc())
    )
    stmt = _apply_send_log_period_filter(stmt, from_date, to_date)
    rows = (await db.execute(stmt)).all()

    return [
        {
            "error_code": row.error_code,
            "count": _to_int(row.count),
            "last_attempted_at": row.last_attempted_at,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# 4) 메시지 텍스트 검색
# ---------------------------------------------------------------------------


async def search_messages(
    db: AsyncSession,
    *,
    query: str,
    from_date: date_cls | None,
    to_date: date_cls | None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """메시지 텍스트 검색 (대소문자 무관 ILIKE).

    매칭 대상: ``DistributionMessage.content`` OR ``edited_content``.
    반환: ``[{message_id, session_id, scenario_name, sender_account_label,
              content, sent_at, status}]`` — 최신순(``generated_at`` DESC).

    응답의 ``content`` 는 ``edited_content`` 우선 폴백.
    """
    # ILIKE 패턴 — 와일드카드 이스케이프는 SQLAlchemy/psycopg 가 처리.
    pattern = f"%{query}%"

    stmt = (
        select(
            DistributionMessage.id.label("message_id"),
            DistributionMessage.session_id.label("session_id"),
            DistributionScenario.name.label("scenario_name"),
            DistributionPersona.account_label.label("sender_account_label"),
            DistributionMessage.content.label("content"),
            DistributionMessage.edited_content.label("edited_content"),
            DistributionMessage.sent_at.label("sent_at"),
            DistributionMessage.status.label("status"),
        )
        .join(
            DistributionSession,
            DistributionSession.id == DistributionMessage.session_id,
        )
        .join(
            DistributionScenario,
            DistributionScenario.id == DistributionSession.scenario_id,
        )
        .join(
            DistributionPersona,
            DistributionPersona.id == DistributionMessage.sender_persona_id,
        )
        .where(
            or_(
                DistributionMessage.content.ilike(pattern),
                DistributionMessage.edited_content.ilike(pattern),
            )
        )
        .order_by(DistributionSession.generated_at.desc())
        .limit(limit)
    )
    stmt = _apply_message_period_filter(stmt, from_date, to_date)
    rows = (await db.execute(stmt)).all()

    return [
        {
            "message_id": row.message_id,
            "session_id": row.session_id,
            "scenario_name": row.scenario_name,
            "sender_account_label": row.sender_account_label,
            # edited_content 우선 — 운영자가 편집한 최종 문구를 노출.
            "content": row.edited_content or row.content,
            "sent_at": row.sent_at,
            "status": row.status,
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# 5) 세션 상태별 카운트 (dict)
# ---------------------------------------------------------------------------


async def session_count_by_status(
    db: AsyncSession,
    *,
    from_date: date_cls | None,
    to_date: date_cls | None,
) -> dict[str, int]:
    """status 별 세션 카운트 dict.

    반환: ``{pending: int, approved: int, rejected: int, sending: int, sent: int, failed: int}``
    — 6종 키 모두 항상 포함 (0건도 누락 X).
    """
    stmt = select(
        DistributionSession.status.label("status"),
        func.count(DistributionSession.id).label("count"),
    ).group_by(DistributionSession.status)
    stmt = _apply_session_period_filter(stmt, from_date, to_date)
    rows = (await db.execute(stmt)).all()

    counts = {row.status: _to_int(row.count) for row in rows}
    return {status: counts.get(status, 0) for status in SESSION_STATUS_KEYS}
