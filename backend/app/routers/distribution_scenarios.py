"""신사업유통 시나리오 조회/생성 라우터 (T9 Phase E-2 → 2026-06-01 사용자 작성).

생성 트리거 모달에서 선택할 시나리오 목록 + 사용자가 자연어 지시로 직접
시나리오를 만드는 경로를 제공한다.

엔드포인트:
- GET  /api/distribution/scenarios   → 활성 시나리오 간단 목록 (사용자 작성분 포함)
- POST /api/distribution/scenarios   → 자연어 지시 기반 사용자 시나리오 생성(저장형)
"""
from __future__ import annotations

import logging
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_module
from app.models.distribution import DistributionScenario
from app.modules.constants import Module

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/distribution",
    tags=["distribution-scenarios"],
    # T9 라우터 가드 정책 통일: 시나리오 조회/생성 — 신사업팀 사용 가능.
    dependencies=[Depends(require_module(Module.DISTRIBUTION.value))],
)


class ScenarioBrief(BaseModel):
    """모달용 시나리오 간단 응답.

    사용자 작성 시나리오(instruction 보유)는 미리보기를 위해 instruction 도 노출.
    """

    id: uuid.UUID
    name: str
    trigger_event: str
    sender_role: str
    receiver_role: str
    # 시나리오 기본 언어 ('ko' | 'zh'). 모달 기본 언어 힌트.
    language: str = "ko"
    # 첨부 권장 시나리오 여부 (검수 UI 배너).
    attachment_required: bool = False
    # 사용자 자유 텍스트 지시 (있으면 사용자 작성 시나리오).
    instruction: str | None = None

    model_config = {"from_attributes": True}


class UserScenarioCreate(BaseModel):
    """자연어 지시 기반 사용자 시나리오 생성 요청(저장형).

    beats 를 코딩하지 않고 instruction 자유 텍스트만으로 동작한다.
    instruction 은 한국어로 써도 되고, 실제 대화는 language(기본 zh)로 생성된다.
    """

    name: str = Field(min_length=1, max_length=100)
    instruction: str = Field(min_length=1, max_length=20_000)
    sender_role: Literal["domestic_admin", "vietnam_admin"] = "domestic_admin"
    receiver_role: Literal["domestic_admin", "vietnam_admin"] = "vietnam_admin"
    language: Literal["ko", "zh"] = "zh"
    attachment_required: bool = False


@router.get("/scenarios")
async def list_scenarios_endpoint(
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[ScenarioBrief]]:
    """활성 시나리오 간단 목록 (생성 트리거 모달용).

    노출 대상 (2026-06-01): active=True 이고 (사용자 작성분(instruction 보유)
    이거나 한국어 시드(language='ko')). 중국어 트윈 시드(instruction 없음 +
    language='zh')는 few-shot 내부 재사용 전용이라 picker 에서 숨긴다.
    """
    stmt = (
        select(DistributionScenario)
        .where(
            DistributionScenario.active.is_(True),
            or_(
                DistributionScenario.instruction.isnot(None),
                DistributionScenario.language == "ko",
            ),
        )
        .order_by(DistributionScenario.name)
    )
    rows = await db.execute(stmt)
    items = [ScenarioBrief.model_validate(s) for s in rows.scalars().all()]
    return {"items": items}


@router.post("/scenarios", status_code=status.HTTP_201_CREATED)
async def create_user_scenario(
    body: UserScenarioCreate,
    db: AsyncSession = Depends(get_db),
) -> ScenarioBrief:
    """자연어 지시 기반 사용자 시나리오 생성 (저장형, active=True → picker 노출).

    beats 는 비우고(instruction 으로 흐름 가이드), trigger_event='custom'.
    동일 active name 이 있으면 409.
    """
    dup = await db.execute(
        select(DistributionScenario).where(
            DistributionScenario.name == body.name,
            DistributionScenario.active.is_(True),
        )
    )
    if dup.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"이미 같은 이름의 활성 시나리오가 있습니다: {body.name}",
        )

    scenario = DistributionScenario(
        name=body.name,
        trigger_event="custom",
        sender_role=body.sender_role,
        receiver_role=body.receiver_role,
        beats=[],
        example_msgs=None,
        instruction=body.instruction,
        raw_text=None,
        language=body.language,
        active=True,
        attachment_required=body.attachment_required,
    )
    db.add(scenario)
    await db.commit()
    await db.refresh(scenario)
    logger.info("distribution.scenario: 사용자 시나리오 생성 name=%s", scenario.name)
    return ScenarioBrief.model_validate(scenario)
