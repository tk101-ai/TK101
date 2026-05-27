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
from app.dependencies import require_module
from app.models.distribution import DistributionScenario
from app.modules.constants import Module

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/distribution",
    tags=["distribution-scenarios"],
    # T9 라우터 가드 정책 통일: 시나리오 목록 조회 — 신사업팀 사용 가능.
    dependencies=[Depends(require_module(Module.DISTRIBUTION.value))],
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
    # 시나리오 기본 언어 (T9 — 2026-05-27). 'ko' | 'zh'. 모달에서 기본 언어 힌트로 사용.
    language: str = "ko"

    model_config = {"from_attributes": True}


@router.get("/scenarios")
async def list_scenarios_endpoint(
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[ScenarioBrief]]:
    """활성 시나리오 간단 목록 (생성 트리거 모달용).

    name 알파벳 정렬. 비활성(active=False) 시나리오는 제외.

    언어 필터 (T9 — 2026-05-27): 한국어(language='ko') 업무 시나리오만 노출한다.
    중국어(language='zh') 시드는 모달 선택지에서 숨기고, 생성 시 ko 시나리오 +
    中文 선택 조합에서 trigger_event 로 매칭하여 few-shot 으로만 내부 재사용한다.
    (zh 시드를 picker 에서 제거하면 중복 15행 → ko 8행으로 정리됨.)
    """
    stmt = (
        select(DistributionScenario)
        .where(
            DistributionScenario.active.is_(True),
            DistributionScenario.language == "ko",
        )
        .order_by(DistributionScenario.name)
    )
    rows = await db.execute(stmt)
    items = [ScenarioBrief.model_validate(s) for s in rows.scalars().all()]
    return {"items": items}
