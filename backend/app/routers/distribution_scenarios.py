"""신사업유통 시나리오 조회 라우터 (T9 Phase E-2).

생성 트리거 모달에서 사용자가 선택할 시나리오 목록을 노출하기 위한 간이 조회 API.
기존 시나리오 CRUD 가 아직 노출되지 않은 상태라 모달용 슬림 응답만 제공.

엔드포인트:
- GET /api/distribution/scenarios → 활성 시나리오 간단 목록
"""
from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.distribution import DistributionScenario

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/distribution",
    tags=["distribution-scenarios"],
    dependencies=[Depends(require_admin)],
)


class ScenarioBrief(BaseModel):
    """모달용 시나리오 간단 응답.

    전체 ScenarioOut 은 beats / example_msgs / raw_text 까지 포함하지만,
    트리거 모달은 선택용 식별자만 필요하므로 슬림하게 노출.
    """

    id: uuid.UUID
    name: str
    trigger_event: str
    sender_role: str
    receiver_role: str

    model_config = {"from_attributes": True}


@router.get("/scenarios")
async def list_scenarios_endpoint(
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[ScenarioBrief]]:
    """활성 시나리오 간단 목록 (생성 트리거 모달용).

    name 알파벳 정렬. 비활성(active=False) 시나리오는 제외.
    """
    stmt = (
        select(DistributionScenario)
        .where(DistributionScenario.active.is_(True))
        .order_by(DistributionScenario.name)
    )
    rows = await db.execute(stmt)
    items = [ScenarioBrief.model_validate(s) for s in rows.scalars().all()]
    return {"items": items}
