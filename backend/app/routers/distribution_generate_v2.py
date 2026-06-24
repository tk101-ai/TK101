"""커스텀 생성 트리거 (T9 Phase E-2 → F-B 시나리오 합성).

기존 ``/generate-weekly`` 는 활성 한국 페르소나 전체 × 기본 시나리오 2개를 자동 사용.
본 endpoint 는 사용자가 명시한 페르소나 + 시나리오로만 생성한다.

Phase F-B 변경 (시나리오 합성):
- 이전: 페르소나 × 시나리오 = N×M 세션 (시나리오마다 LLM 1회).
- 이제: 페르소나당 1 세션 — 선택된 시나리오 N개를 하나의 대화에 자연스럽게 합성.
  LLM 호출 수 = 페르소나 수 (시나리오 수 무관). 비용 1/N.

흐름:
1. payload.sender_persona_ids → role=domestic_admin 검증 후 페르소나 조회.
2. 활성 vietnam_admin 1명 자동 선택 (자격증명 보유 + active=True).
3. payload.scenario_names → active=True 만 통과.
4. 페르소나별로 시나리오 N개를 합성하여 1세션 생성
   (``_create_one_pair_combined_session``).
5. 결과 `GenerateCustomResult` 반환.
"""
from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_module
from app.models.distribution import (
    DistributionPersona,
    DistributionScenario,
)
from app.models.user import User
from app.modules.constants import Module
from app.services.distribution.conversation_generator import GenerationError
from app.services.distribution.generation_service import (
    _create_one_pair_combined_session,
    _has_credentials,
    _label_or_id,
)
from app.services.translation.translator import (
    RateLimitExceeded,
    check_rate_limit,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/distribution",
    tags=["distribution-generate"],
    # T9 라우터 가드 정책 통일: 생성은 LLM만 호출 (실 송신 X) → 신사업팀 사용 가능.
    dependencies=[Depends(require_module(Module.DISTRIBUTION.value))],
)


# D2: LLM 생성 비용 폭주 차단. 사용자별 분당/일일 호출 한도.
# translator.check_rate_limit(인메모리 슬라이딩 윈도우) 재사용 — 단일 인스턴스 전제.
# 일일 캡은 window_sec=86400 으로 같은 util 을 재사용하되, 분당 버킷과
# 충돌하지 않도록 키에 ":daily" 접미사를 붙인다.
_GEN_PER_MIN_MAX = 5
_GEN_DAILY_MAX = 50
_GEN_DAILY_WINDOW_SEC = 86_400


def _enforce_generation_limit(user_id: str) -> None:
    """생성 엔드포인트 공통 레이트리밋 (분당 + 일일 캡).

    Raises:
        HTTPException(429): 분당 또는 일일 한도 초과.
    """
    try:
        check_rate_limit(
            f"distgen:{user_id}",
            max_calls=_GEN_PER_MIN_MAX,
            window_sec=60,
        )
        check_rate_limit(
            f"distgen:daily:{user_id}",
            max_calls=_GEN_DAILY_MAX,
            window_sec=_GEN_DAILY_WINDOW_SEC,
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="생성 요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.",
        ) from exc


class GenerateCustomRequest(BaseModel):
    """커스텀 생성 요청.

    sender_persona_ids 는 첫 발송 계정 목록이다.
    활성·자격증명·로그인 완료 계정만 실제 생성 대상이 된다.
    """

    sender_persona_ids: list[UUID] = Field(min_length=1)
    # 저장형 시나리오 이름 목록. 즉석(ad_hoc_instruction) 사용 시 비워도 됨.
    scenario_names: list[str] = Field(default_factory=list)
    # 즉석 지시(저장 안 함) — 있으면 active=False 숨김 시나리오를 자동 생성해 사용.
    ad_hoc_instruction: str | None = Field(default=None, max_length=20_000)
    # 그룹 송신 (T9 — 2026-06-01). 설정 시 생성 세션이 1:1 DM 대신 이 텔레그램
    # 그룹(chat id / @username / t.me 링크)에 게시된다(3명 방). None=1:1.
    group_chat_id: str | None = Field(default=None, max_length=64)
    # 메시지 간격 분포 (T9 — 2026-05-26).
    # short: 0~30분 빠른 핑퐁 / normal: 5분~3시간 / varied: 1분~12시간 폭넓게.
    timing_profile: Literal["short", "normal", "varied"] = "normal"
    # 대화 언어 (T9 — 2026-05-27). ko=한국어(기본) | zh=간체 중국어.
    # 시나리오 language 컬럼보다 사용자 선택값을 우선 적용한다.
    language: Literal["ko", "zh"] = "ko"


class GenerateCustomResult(BaseModel):
    """커스텀 생성 결과."""

    sessions_created: list[UUID] = Field(default_factory=list)
    skipped: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 컨텍스트 조회 헬퍼
# ---------------------------------------------------------------------------


async def _personas_by_ids(
    db: AsyncSession, *, ids: list[UUID]
) -> list[DistributionPersona]:
    """지정 ID 페르소나 조회 (account_label 정렬)."""
    if not ids:
        return []
    stmt = (
        select(DistributionPersona)
        .where(DistributionPersona.id.in_(ids))
        .order_by(DistributionPersona.account_label)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def _pick_active_vietnam_admin(
    db: AsyncSession,
) -> DistributionPersona | None:
    """활성 베트남 어드민 1명 (자격증명 有 우선)."""
    stmt = (
        select(DistributionPersona)
        .where(
            DistributionPersona.role == "vietnam_admin",
            DistributionPersona.active.is_(True),
        )
        .order_by(DistributionPersona.account_label)
    )
    res = await db.execute(stmt)
    candidates = list(res.scalars().all())
    if not candidates:
        return None
    # 자격증명 있는 페르소나를 우선 선택.
    for p in candidates:
        if _has_credentials(p):
            return p
    return candidates[0]


def _is_logged_in(p: DistributionPersona) -> bool:
    """로그인(세션) 완료 여부 — session_path + telegram_user_id 둘 다 있어야."""
    return bool(p.session_path) and bool(p.telegram_user_id)


async def _pick_counterpart(
    db: AsyncSession, sender: DistributionPersona
) -> DistributionPersona | None:
    """발신 sender 의 대화 상대(수신) 1명 자동 선택 (2026-06-08).

    상대는 sender 와 다른 활성·자격증명 보유·로그인 완료 계정 중에서 고른다.
    공급 방향(한국=공급/베트남=수령) 일관성을 위해 반대 역할을 우선한다.
    """
    stmt = (
        select(DistributionPersona)
        .where(
            DistributionPersona.id != sender.id,
            DistributionPersona.active.is_(True),
        )
        .order_by(DistributionPersona.account_label)
    )
    res = await db.execute(stmt)
    candidates = [
        p for p in res.scalars().all() if _has_credentials(p) and _is_logged_in(p)
    ]
    if not candidates:
        return None
    opposite = (
        "vietnam_admin" if sender.role == "domestic_admin" else "domestic_admin"
    )
    candidates.sort(key=lambda p: p.role == opposite, reverse=True)
    return candidates[0]


async def _scenarios_by_names_active(
    db: AsyncSession, *, names: list[str]
) -> list[DistributionScenario]:
    """active=True 시나리오만, names 순서 보존."""
    if not names:
        return []
    stmt = select(DistributionScenario).where(
        DistributionScenario.name.in_(names),
        DistributionScenario.active.is_(True),
    )
    res = await db.execute(stmt)
    by_name = {s.name: s for s in res.scalars().all()}
    return [by_name[n] for n in names if n in by_name]


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------


@router.post("/generate-custom")
async def generate_custom(
    payload: GenerateCustomRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GenerateCustomResult:
    """사용자가 명시한 (페르소나 × 시나리오) 조합으로 세션 생성.

    권한: DISTRIBUTION 모듈(admin + 신사업팀). LLM 생성 비용은 사용자별 분당/일일 호출 한도로 가드(D2).

    검증:
    - 계정 미존재/비활성/미로그인은 errors 또는 skipped 에 기록 후 진행.
    - 대화 상대가 될 다른 활성·로그인 계정이 없으면 해당 계정은 skipped.
    """
    _enforce_generation_limit(str(user.id))
    result = GenerateCustomResult()

    # 1. 첫 발송 계정 조회.
    #    활성·자격증명·로그인 완료 계정만 실제 생성 대상으로 사용한다.
    #    상대는 _pick_counterpart 로 발신마다 반대역할·로그인 완료 계정 우선 자동 선택.
    requested = await _personas_by_ids(db, ids=payload.sender_persona_ids)
    found_ids = {p.id for p in requested}
    missing_ids = [pid for pid in payload.sender_persona_ids if pid not in found_ids]
    for pid in missing_ids:
        result.errors.append(f"텔레그램 계정 {pid}: 존재하지 않음")

    sender_personas: list[DistributionPersona] = list(requested)
    if not sender_personas:
        result.errors.append("유효한 첫 발송 계정이 없습니다.")
        return result

    # 비즈니스 컨텍스트(주차 요약 weekly_summary)는 더 이상 생성에 사용하지 않는다.
    bl_ctx = None

    # 시나리오 조회.
    scenarios = await _scenarios_by_names_active(db, names=payload.scenario_names)
    missing_scenarios = set(payload.scenario_names) - {s.name for s in scenarios}
    for name in missing_scenarios:
        result.errors.append(f"시나리오 '{name}': 존재하지 않거나 비활성")

    # 4-b. 즉석 지시(ad-hoc): 숨김 시나리오(active=False) 자동 생성 후 사용.
    #      세션은 시나리오를 반드시 참조(NOT NULL)하므로 저장하지 않는 즉석도 행이 필요.
    if payload.ad_hoc_instruction and payload.ad_hoc_instruction.strip():
        instruction = payload.ad_hoc_instruction.strip()
        ad_hoc = DistributionScenario(
            name=f"[즉석] {instruction[:60]}",
            trigger_event="custom",
            sender_role="domestic_admin",
            receiver_role="vietnam_admin",
            beats=[],
            example_msgs=None,
            instruction=instruction,
            raw_text=None,
            language=payload.language,
            active=False,
        )
        db.add(ad_hoc)
        await db.flush()
        scenarios.append(ad_hoc)

    if not scenarios:
        result.errors.append("실행 가능한 시나리오 없음 (시나리오 선택 또는 즉석 지시 입력 필요).")
        return result

    # 5. 첫 발송 계정별 1 세션 생성 (시나리오 N개 합성, Phase F-B). 실패 격리.
    scenario_names_str = " + ".join(s.name for s in scenarios)
    for sender in sender_personas:
        sender_label = _label_or_id(sender)
        if not sender.active:
            result.skipped.append(f"{sender_label}: 비활성 계정")
            continue
        if not _has_credentials(sender):
            result.skipped.append(f"{sender_label}: 자격증명 없음")
            continue
        if not _is_logged_in(sender):
            result.skipped.append(f"{sender_label}: 텔레그램 로그인 필요")
            continue

        # 발신마다 상대를 자동 선택 — 반대역할·로그인 완료 계정 우선, 자신 제외.
        vn_persona = await _pick_counterpart(db, sender)
        if vn_persona is None:
            result.skipped.append(
                f"{sender_label}: 대화 상대가 될 다른 활성·로그인 계정이 없습니다."
            )
            continue

        try:
            session_id = await _create_one_pair_combined_session(
                db,
                scenarios=scenarios,
                kr_persona=sender,
                vn_persona=vn_persona,
                bl_ctx=bl_ctx,
                timing_profile=payload.timing_profile,
                language=payload.language,
                group_chat_id=payload.group_chat_id,
            )
            result.sessions_created.append(UUID(session_id))
            logger.info(
                "distribution.custom: session=%s pair=%s↔%s scenarios=%s 생성(합성)",
                session_id,
                sender_label,
                vn_persona.account_label,
                scenario_names_str,
            )
        except GenerationError as exc:
            msg = f"{sender_label} / 합성({scenario_names_str}): {exc}"
            result.errors.append(msg)
            logger.warning("distribution.custom: 생성 실패 — %s", msg)
        except Exception as exc:  # noqa: BLE001 — 페르소나 단위 격리
            msg = (
                f"{sender_label} / 합성({scenario_names_str}): "
                f"예기치 못한 오류 ({type(exc).__name__})"
            )
            result.errors.append(msg)
            logger.exception("distribution.custom: 예외 — %s", msg)

    # 6. 커밋 (개별 flush 는 _create_one_pair_combined_session 내부에서 수행됨).
    if result.sessions_created:
        try:
            await db.commit()
        except Exception:
            logger.exception("distribution.custom: 커밋 실패 — 롤백")
            await db.rollback()
            result.errors.append("DB 커밋 실패 — 모든 세션 롤백됨")
            result.sessions_created.clear()
    else:
        await db.rollback()

    return result
