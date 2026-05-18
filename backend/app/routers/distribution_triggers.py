"""트리거/fingerprint 라우터 (T9 Phase D).

main.py 에서 별도 include:
  app.include_router(distribution_triggers.router)

엔드포인트:
- GET /api/distribution/fingerprint — 현재 데이터 fingerprint 조회 (디버깅용)
- GET /api/distribution/trigger-status — 오늘이 트리거 일자인지 + 다음 트리거 일자
- POST /api/distribution/check-and-generate body {previous_fingerprint?} —
  데이터 변경 여부 검사 + 트리거 일자 검사. 둘 중 하나라도 만족하면 generation_service 호출 후보로 표시 (실제 트리거는 v0.3).
"""
from __future__ import annotations

import logging
from datetime import date as date_cls

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.services.distribution.calendar_helper import (
    adjusted_trigger_dates, is_trigger_today,
)
from app.services.distribution.fingerprint_service import (
    compute_fingerprint, has_changed_since,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/distribution",
    tags=["distribution-triggers"],
    dependencies=[Depends(require_admin)],
)


class FingerprintOut(BaseModel):
    fingerprint: str
    weekly_count: int
    product_count: int
    latest_period_label: str | None


class TriggerStatusOut(BaseModel):
    is_trigger_today: bool
    today: date_cls
    next_triggers: list[date_cls]  # 이번 달 + 다음 달 일부 합쳐 상위 5


class CheckGenerateRequest(BaseModel):
    previous_fingerprint: str | None = None


class CheckGenerateResult(BaseModel):
    data_changed: bool
    is_trigger_today: bool
    should_generate: bool  # 둘 중 하나라도 True
    current: FingerprintOut


@router.get("/fingerprint")
async def get_fingerprint(db: AsyncSession = Depends(get_db)) -> FingerprintOut:
    r = await compute_fingerprint(db)
    return FingerprintOut(**r.__dict__)


@router.get("/trigger-status")
async def get_trigger_status() -> TriggerStatusOut:
    today = date_cls.today()
    # 이번 달 + 다음 달 트리거 일자 중 오늘 이후 5개
    upcoming = [d for d in adjusted_trigger_dates(today.year, today.month) if d >= today]
    # 다음 달도 일부 추가
    nm = today.month + 1
    ny = today.year if nm <= 12 else today.year + 1
    if nm > 12:
        nm = 1
    upcoming.extend(adjusted_trigger_dates(ny, nm))
    return TriggerStatusOut(
        is_trigger_today=is_trigger_today(today),
        today=today,
        next_triggers=upcoming[:5],
    )


@router.post("/check-and-generate")
async def check_and_generate(
    payload: CheckGenerateRequest,
    db: AsyncSession = Depends(get_db),
) -> CheckGenerateResult:
    changed, current = await has_changed_since(
        db, previous_fingerprint=payload.previous_fingerprint
    )
    is_trig = is_trigger_today(date_cls.today())
    return CheckGenerateResult(
        data_changed=changed,
        is_trigger_today=is_trig,
        should_generate=changed or is_trig,
        current=FingerprintOut(**current.__dict__),
    )
