"""주간 대화 생성 오케스트레이터 (T9 Phase B-2).

흐름:
1. 최신 weekly_summary 1행 + 활성 products 일부(상위 N) 컨텍스트로 구성.
2. 활성 한국 페르소나(KR-A1~A4) × 베트남 페르소나 1명 × 시나리오 N개 조합으로
   각각 1세션을 생성 (1:1 페어 토폴로지).
3. status='pending' 으로 저장 → 어드민이 UI 에서 검수 후 승인.

세션 생성 단위:
- (sender_persona, receiver_persona, scenario) 조합 1개 = 세션 1개.
- 보통 한 페르소나당 1~2 시나리오만 사용 (안 그러면 너무 많은 메시지).

호환성:
- scenario_engine.BlContext 시그니처를 깨지 않기 위해, weekly_summary 컨텍스트는
  BlContext.product 필드에 "매입 X원, 입금요청 Y원, 재고이동 ..." 형태의 요약 텍스트로
  주입한다 (기존 LLM 프롬프트는 ``- 품목: ...`` 로 그대로 노출됨 → Claude 가 본문에 활용).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import (
    DistributionMessage,
    DistributionPersona,
    DistributionProduct,
    DistributionScenario,
    DistributionSession,
    DistributionWeeklySummary,
)
from app.services.distribution.conversation_generator import (
    GenerationError,
    GenerationResult,
    generate_conversation,
)
from app.services.distribution.scenario_engine import (
    BlContext,
    PersonaContext,
    ScenarioContext,
    merge_scenario_contexts,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

# 기본 시나리오 화이트리스트 — 주간 생성 시 자동 사용.
DEFAULT_WEEKLY_SCENARIOS: tuple[str, ...] = (
    "주간 정산 요약",
    "명품 추가 매입 요청",
)

# 명품재고대장에서 멘션용으로 가져올 상위 제품 개수.
TOP_PRODUCT_LIMIT: int = 12

# 당장은 베트남(VN-A)과 TK(KR-A1) 두 계정만 대화에 참여시킨다 (2026-05-27 사용자 결정).
# 향후 KR-A2~A4 등 다른 계정을 추가하려면 이 튜플에 account_label 만 더하면 됨.
# 빈 튜플이거나 매칭되는 라벨이 DB 에 없으면 화이트리스트를 적용하지 않고
# 기존 동작(role 별 전체 활성 페르소나)을 유지한다 — 하위호환.
DISTRIBUTION_ACTIVE_ACCOUNT_LABELS: tuple[str, ...] = ("VN-A", "KR-A1")


@dataclass
class GenerationSummary:
    """4페어 주간 생성 결과 요약."""

    sessions_created: list[str] = field(default_factory=list)  # uuid string
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# 컨텍스트 조회 헬퍼
# ---------------------------------------------------------------------------


async def _latest_weekly_summary(
    db: AsyncSession, *, company_label: str
) -> DistributionWeeklySummary | None:
    """company_label 의 가장 최근 weekly_summary 1행 조회."""
    stmt = (
        select(DistributionWeeklySummary)
        .where(DistributionWeeklySummary.company_label == company_label)
        .order_by(desc(DistributionWeeklySummary.period_end))
        .limit(1)
    )
    res = await db.execute(stmt)
    return res.scalar_one_or_none()


async def _top_products(db: AsyncSession, *, limit: int) -> list[DistributionProduct]:
    """국내 재고 수량이 많은 순으로 상위 N개 제품 조회 (멘션용)."""
    stmt = (
        select(DistributionProduct)
        .where(DistributionProduct.domestic_stock_qty.isnot(None))
        .order_by(desc(DistributionProduct.domestic_stock_qty))
        .limit(limit)
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def _active_personas_by_role(
    db: AsyncSession, *, role: str
) -> list[DistributionPersona]:
    """role 별 활성 페르소나 목록 (account_label 정렬).

    당장은 베트남(VN-A)·TK(KR-A1)만 운영하므로
    ``DISTRIBUTION_ACTIVE_ACCOUNT_LABELS`` 화이트리스트로 한 번 더 걸러낸다.
    단, 화이트리스트와 매칭되는 라벨이 하나도 없으면(아직 시드 안 됨 등)
    화이트리스트를 무시하고 role 전체를 반환해 기존 동작을 보존한다(하위호환).
    """
    stmt = (
        select(DistributionPersona)
        .where(
            DistributionPersona.role == role,
            DistributionPersona.active.is_(True),
        )
        .order_by(DistributionPersona.account_label)
    )
    res = await db.execute(stmt)
    personas = list(res.scalars().all())

    if not DISTRIBUTION_ACTIVE_ACCOUNT_LABELS:
        return personas
    whitelisted = [
        p
        for p in personas
        if p.account_label in DISTRIBUTION_ACTIVE_ACCOUNT_LABELS
    ]
    # 화이트리스트 매칭이 0건이면 라벨이 아직 다를 수 있으므로 원본 그대로 반환.
    return whitelisted if whitelisted else personas


async def _scenarios_by_names(
    db: AsyncSession, *, names: Sequence[str]
) -> list[DistributionScenario]:
    """name 화이트리스트로 활성 시나리오 조회. 순서는 names 순서 보존."""
    if not names:
        return []
    stmt = select(DistributionScenario).where(
        DistributionScenario.name.in_(list(names)),
        DistributionScenario.active.is_(True),
    )
    res = await db.execute(stmt)
    by_name = {s.name: s for s in res.scalars().all()}
    return [by_name[n] for n in names if n in by_name]


# ---------------------------------------------------------------------------
# 컨텍스트 직렬화
# ---------------------------------------------------------------------------


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return "미정"
    # 천단위 콤마, 소수점 제거 (원 단위).
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _summary_text(summary: DistributionWeeklySummary) -> str:
    """weekly_summary 의 핵심 필드를 한 줄 텍스트로 직렬화.

    BlContext.product 필드에 주입되어 프롬프트의 ``- 품목: ...`` 라인으로 노출됨.
    Claude 가 이 텍스트를 본문에 자연스럽게 풀어 사용함.
    """
    parts = [
        f"[{summary.period_label}]",
        f"매입 {_fmt_money(summary.kr_purchase)}원",
        f"매입 입금요청 {_fmt_money(summary.kr_purchase_deposit_req)}원",
        f"재고이동 {_fmt_money(summary.vn_inventory_move)}원",
        f"재고이동 입금요청 {_fmt_money(summary.vn_inventory_deposit_req)}원",
        f"매출완료 {_fmt_money(summary.vn_sales_completed)}원",
        f"매출 입금요청 {_fmt_money(summary.vn_sales_deposit_req)}원",
    ]
    return ", ".join(parts)


def _products_text(products: Sequence[DistributionProduct]) -> str:
    """상위 제품 목록을 짧은 텍스트로 직렬화 (멘션용)."""
    if not products:
        return ""
    items: list[str] = []
    for p in products[:TOP_PRODUCT_LIMIT]:
        label = p.brand
        if p.category:
            label = f"{label}({p.category})"
        if p.domestic_stock_qty is not None:
            label = f"{label} 재고 {p.domestic_stock_qty}"
        items.append(label)
    return " / ".join(items)


def _build_bl_context(
    summary: DistributionWeeklySummary | None,
    products: Sequence[DistributionProduct],
) -> BlContext:
    """weekly_summary + products 를 BlContext 로 패킹.

    기존 BlContext 시그니처를 깨지 않으면서 주간 컨텍스트를 LLM 에 전달하는 우회.
    - product: 주간 요약 + 상위 제품 라벨
    - quantity: 상위 제품 1위 재고 수량 (있을 때)
    - destination: company_label
    - 나머지(BL/컨테이너/일자): None
    """
    summary_str = _summary_text(summary) if summary else "주간 요약 없음"
    products_str = _products_text(products)
    product_field = summary_str
    if products_str:
        product_field = f"{summary_str}; 상위 재고 — {products_str}"

    top_qty: int | None = None
    if products:
        for p in products:
            if p.domestic_stock_qty is not None:
                top_qty = int(p.domestic_stock_qty)
                break

    destination = summary.company_label if summary else None

    return BlContext(
        bl_number=None,
        container_no=None,
        product=product_field,
        quantity=top_qty,
        departure_date=None,
        arrival_date=None,
        destination=destination,
    )


def _persona_context(persona: DistributionPersona) -> PersonaContext:
    return PersonaContext(
        account_label=persona.account_label,
        role=persona.role,
        display_name=persona.display_name,
        tone_profile=persona.tone_profile,
    )


def _scenario_context(scenario: DistributionScenario) -> ScenarioContext:
    return ScenarioContext(
        name=scenario.name,
        trigger_event=scenario.trigger_event,
        beats=scenario.beats or [],
        example_msgs=scenario.example_msgs,
        raw_text=scenario.raw_text,
        instruction=getattr(scenario, "instruction", None),
    )


def _scenario_language(scenario: DistributionScenario) -> str:
    """시나리오의 language 컬럼 정규화 ('ko'|'zh'). 미지정/이상값은 'ko' 폴백."""
    lang = (getattr(scenario, "language", None) or "ko").lower()
    return "zh" if lang == "zh" else "ko"


async def _zh_counterparts_by_trigger(
    db: AsyncSession,
) -> dict[str, DistributionScenario]:
    """중국어(language='zh') 시드를 trigger_event 키로 조회 (few-shot 재사용용).

    T9 — 2026-05-27: 모달 picker 에는 ko 업무 시나리오만 노출하되, 사용자가
    ko 시나리오 + 中文 을 선택하면 동일 trigger_event 의 zh 시드를 찾아
    그 beats / example_msgs 를 중국어 few-shot 으로 재사용한다.
    동일 trigger_event 가 여러 zh 시드에 있으면 name 정렬 첫 번째를 채택한다.
    """
    stmt = (
        select(DistributionScenario)
        .where(
            DistributionScenario.active.is_(True),
            DistributionScenario.language == "zh",
        )
        .order_by(DistributionScenario.name)
    )
    res = await db.execute(stmt)
    mapping: dict[str, DistributionScenario] = {}
    for sc in res.scalars().all():
        # 먼저 들어온 것을 유지 (name 정렬 기준 첫 번째).
        mapping.setdefault(sc.trigger_event, sc)
    return mapping


def _scenario_context_for_language(
    scenario: DistributionScenario,
    *,
    language: str,
    zh_twins: dict[str, DistributionScenario] | None,
) -> ScenarioContext:
    """언어에 맞춰 few-shot 소스를 고른 ScenarioContext 반환.

    - language='zh' 이고 동일 trigger_event 의 zh 트윈이 있으면 그 beats /
      example_msgs 를 사용 (큐레이션된 중국어 예시 재사용). 단, name / trigger_event 는
      ko 원본을 그대로 유지해 추적성을 지킨다.
    - zh 트윈이 없으면(예: weekly_settlement) ko 시나리오 beats 로 폴백하고
      프롬프트만 중국어로 생성한다.
    - language='ko' 이면 원본 ko 시나리오를 그대로 사용.
    """
    if language == "zh" and zh_twins:
        twin = zh_twins.get(scenario.trigger_event)
        if twin is not None:
            return ScenarioContext(
                name=scenario.name,
                trigger_event=scenario.trigger_event,
                beats=twin.beats or scenario.beats or [],
                example_msgs=twin.example_msgs
                if twin.example_msgs
                else scenario.example_msgs,
                raw_text=twin.raw_text or scenario.raw_text,
                # 사용자 지시는 원본 시나리오 것을 유지 (사용자 시나리오는 트윈 없음).
                instruction=getattr(scenario, "instruction", None),
            )
    return _scenario_context(scenario)


# ---------------------------------------------------------------------------
# 자격증명 가드
# ---------------------------------------------------------------------------


def _has_credentials(persona: DistributionPersona) -> bool:
    """자격증명이 등록된 페르소나만 생성 대상.

    api_id_enc / api_hash_enc 둘 다 있어야 송신이 가능하므로
    pending 세션을 생성해도 의미 있는 페르소나만 통과시킨다.
    """
    return bool(persona.api_id_enc) and bool(persona.api_hash_enc)


def _label_or_id(persona: DistributionPersona) -> str:
    return persona.account_label or str(persona.id)


# ---------------------------------------------------------------------------
# 세션 1건 생성 + DB 저장
# ---------------------------------------------------------------------------


def _generate_one_sync(
    *,
    scenario_ctx: ScenarioContext,
    sender_ctx: PersonaContext,
    receiver_ctx: PersonaContext,
    bl_ctx: BlContext | None,
    timing_profile: str = "normal",
    language: str = "ko",
) -> GenerationResult:
    """blocking Claude 호출을 동기 함수에 격리.

    상위에서 ``asyncio.to_thread`` 로 호출하여 이벤트 루프 차단을 피한다.
    language: 'ko'|'zh' — 대화 언어 (시나리오 language 또는 사용자 선택).
    """
    return generate_conversation(
        scenario=scenario_ctx,
        sender=sender_ctx,
        receiver=receiver_ctx,
        bl=bl_ctx,
        timing_profile=timing_profile,  # type: ignore[arg-type]
        language=language,  # type: ignore[arg-type]
    )


async def _create_one_pair_session(
    db: AsyncSession,
    *,
    scenario: DistributionScenario,
    kr_persona: DistributionPersona,
    vn_persona: DistributionPersona,
    bl_ctx: BlContext,
) -> str:
    """1 (kr, vn, scenario) 조합 → 세션 1개 + 메시지 N개 생성/저장.

    Returns 세션 id(str). 실패 시 예외 전파.
    """
    # 시나리오 sender_role 에 따라 발신/수신을 정한다.
    if scenario.sender_role == "domestic_admin":
        sender, receiver = kr_persona, vn_persona
    elif scenario.sender_role == "vietnam_admin":
        sender, receiver = vn_persona, kr_persona
    else:
        # 알 수 없는 role — 한국 출발로 폴백.
        logger.warning(
            "distribution.weekly: 알 수 없는 sender_role=%s, KR 출발로 폴백",
            scenario.sender_role,
        )
        sender, receiver = kr_persona, vn_persona

    sender_ctx = _persona_context(sender)
    receiver_ctx = _persona_context(receiver)
    language = _scenario_language(scenario)
    # zh 시나리오면 동일 trigger_event 의 zh 트윈 few-shot 재사용 (조합 경로와 동일 규칙).
    zh_twins = (
        await _zh_counterparts_by_trigger(db) if language == "zh" else None
    )
    scenario_ctx = _scenario_context_for_language(
        scenario, language=language, zh_twins=zh_twins
    )

    # Claude 호출은 동기 SDK 라 이벤트 루프 분리.
    result: GenerationResult = await asyncio.to_thread(
        _generate_one_sync,
        scenario_ctx=scenario_ctx,
        sender_ctx=sender_ctx,
        receiver_ctx=receiver_ctx,
        bl_ctx=bl_ctx,
        language=language,
    )

    # 발신자 label → persona_id 매핑 (메시지별 sender_persona_id 결정).
    label_to_id: dict[str, Any] = {
        sender.account_label: sender.id,
        receiver.account_label: receiver.id,
    }

    session_row = DistributionSession(
        scenario_id=scenario.id,
        sender_persona_id=sender.id,
        receiver_persona_id=receiver.id,
        status="pending",
        language=language,
        llm_cost_usd=result.cost_usd,
        llm_input_tok=result.input_tokens,
        llm_output_tok=result.output_tokens,
    )
    db.add(session_row)
    await db.flush()  # session_row.id 확보

    for idx, msg in enumerate(result.messages):
        msg_sender_id = label_to_id.get(msg.sender, sender.id)
        db.add(
            DistributionMessage(
                session_id=session_row.id,
                order_index=idx,
                sender_persona_id=msg_sender_id,
                content=msg.content,
                send_after_sec=msg.send_after_sec,
                typing_sec=msg.typing_sec,
                status="queued",
            )
        )

    await db.flush()
    return str(session_row.id)


async def _create_one_pair_combined_session(
    db: AsyncSession,
    *,
    scenarios: list[DistributionScenario],
    kr_persona: DistributionPersona,
    vn_persona: DistributionPersona,
    bl_ctx: BlContext | None,
    timing_profile: str = "normal",
    language: str | None = None,
) -> str:
    """N개 시나리오를 합성하여 1 세션 생성 (페르소나당 1 LLM 호출, Phase F-B).

    동작:
    1. ``merge_scenario_contexts`` 로 합성 ScenarioContext 생성.
    2. 첫 시나리오의 sender_role 로 발신/수신 결정. role 혼재 시 첫 시나리오 기준 + warning.
    3. ``_generate_one_sync`` 로 LLM 1회 호출.
    4. DB 저장 시 session.scenario_id = scenarios[0].id (대표 시나리오). 합성 관계는
       프롬프트 본문(beats intent 접두어)으로만 보존 — 별도 raw_row 메타데이터 컬럼 없음.

    language: 명시되면 그 언어로 생성/기록. None 이면 대표 시나리오의 language 컬럼 사용.

    Returns 세션 id(str). 실패 시 예외 전파.
    """
    if not scenarios:
        raise GenerationError("scenarios 비어있음")

    # 시나리오 sender_role 다양성 체크.
    sender_roles = {s.sender_role for s in scenarios}
    if len(sender_roles) > 1:
        logger.warning(
            "distribution.combined: 시나리오 sender_role 혼재 (%s) — 첫 시나리오 기준 적용",
            sorted(sender_roles),
        )

    primary = scenarios[0]
    if primary.sender_role == "domestic_admin":
        sender, receiver = kr_persona, vn_persona
    elif primary.sender_role == "vietnam_admin":
        sender, receiver = vn_persona, kr_persona
    else:
        logger.warning(
            "distribution.combined: 알 수 없는 sender_role=%s, KR 출발로 폴백",
            primary.sender_role,
        )
        sender, receiver = kr_persona, vn_persona

    # 언어 결정: 명시값 우선, 아니면 대표 시나리오 language 컬럼.
    resolved_language = (
        ("zh" if language.lower() == "zh" else "ko")
        if language is not None
        else _scenario_language(primary)
    )

    # zh 생성이면 trigger_event 로 zh 트윈을 찾아 중국어 few-shot 재사용.
    zh_twins = (
        await _zh_counterparts_by_trigger(db)
        if resolved_language == "zh"
        else None
    )

    merged_name = " + ".join(s.name for s in scenarios)
    merged_ctx = merge_scenario_contexts(
        [
            _scenario_context_for_language(
                s, language=resolved_language, zh_twins=zh_twins
            )
            for s in scenarios
        ],
        name=f"통합({merged_name})",
    )

    sender_ctx = _persona_context(sender)
    receiver_ctx = _persona_context(receiver)

    # Claude 호출은 동기 SDK 라 이벤트 루프 분리.
    result: GenerationResult = await asyncio.to_thread(
        _generate_one_sync,
        scenario_ctx=merged_ctx,
        sender_ctx=sender_ctx,
        receiver_ctx=receiver_ctx,
        bl_ctx=bl_ctx,
        timing_profile=timing_profile,
        language=resolved_language,
    )

    label_to_id: dict[str, Any] = {
        sender.account_label: sender.id,
        receiver.account_label: receiver.id,
    }

    session_row = DistributionSession(
        scenario_id=primary.id,
        sender_persona_id=sender.id,
        receiver_persona_id=receiver.id,
        status="pending",
        language=resolved_language,
        llm_cost_usd=result.cost_usd,
        llm_input_tok=result.input_tokens,
        llm_output_tok=result.output_tokens,
    )
    db.add(session_row)
    await db.flush()

    for idx, msg in enumerate(result.messages):
        msg_sender_id = label_to_id.get(msg.sender, sender.id)
        db.add(
            DistributionMessage(
                session_id=session_row.id,
                order_index=idx,
                sender_persona_id=msg_sender_id,
                content=msg.content,
                send_after_sec=msg.send_after_sec,
                typing_sec=msg.typing_sec,
                status="queued",
            )
        )

    await db.flush()
    return str(session_row.id)


# ---------------------------------------------------------------------------
# 공개 진입점
# ---------------------------------------------------------------------------


async def generate_weekly_for_all_pairs(
    db: AsyncSession,
    *,
    scenario_names: list[str] | None = None,
    company_label: str = "래더엑스",
) -> GenerationSummary:
    """모든 한국 페르소나 × 베트남 페르소나 1명 × 시나리오 조합으로 세션 생성.

    동작:
    1. 최신 weekly_summary 1행 조회 (company_label 일치). 없으면 빈 컨텍스트로 진행.
    2. 활성 페르소나 조회 (domestic_admin 다수 + vietnam_admin 1명).
    3. scenario_names None/빈 리스트면 ``DEFAULT_WEEKLY_SCENARIOS`` 사용.
    4. 자격증명 없는 페르소나는 skip + summary.skipped 에 기록.
    5. 각 조합으로 generate_conversation 호출 + DB 저장(status='pending').
    6. 실패 1건은 다른 조합에 전파되지 않게 격리 (errors 에 누적).

    Returns ``GenerationSummary``.
    """
    summary = GenerationSummary()

    # 1. 컨텍스트 조회
    weekly = await _latest_weekly_summary(db, company_label=company_label)
    if weekly is None:
        logger.warning(
            "distribution.weekly: company_label=%s weekly_summary 없음 — 컨텍스트 없이 생성",
            company_label,
        )
        summary.skipped.append(
            f"weekly_summary[{company_label}]: 데이터 없음 — 빈 컨텍스트로 진행"
        )

    products = await _top_products(db, limit=TOP_PRODUCT_LIMIT)
    bl_ctx = _build_bl_context(weekly, products)

    # 2. 페르소나 조회
    kr_personas = await _active_personas_by_role(db, role="domestic_admin")
    vn_personas = await _active_personas_by_role(db, role="vietnam_admin")

    if not kr_personas:
        summary.skipped.append("domestic_admin: 활성 페르소나 없음")
        return summary
    if not vn_personas:
        summary.skipped.append("vietnam_admin: 활성 페르소나 없음")
        return summary

    # 베트남은 현재 1명 가정. 여러 명이면 첫 번째 사용 + 경고.
    vn_persona = vn_personas[0]
    if len(vn_personas) > 1:
        logger.info(
            "distribution.weekly: vietnam_admin %d명 — 첫 번째(%s)만 페어로 사용",
            len(vn_personas),
            vn_persona.account_label,
        )

    # 3. 시나리오 조회
    target_names = list(scenario_names) if scenario_names else list(DEFAULT_WEEKLY_SCENARIOS)
    scenarios = await _scenarios_by_names(db, names=target_names)
    missing = set(target_names) - {s.name for s in scenarios}
    for name in missing:
        summary.errors.append(f"시나리오 '{name}': 존재하지 않거나 비활성")

    if not scenarios:
        summary.errors.append("실행 가능한 시나리오 없음 — 시드 확인 필요")
        return summary

    # 4. 베트남 자격증명 가드
    if not _has_credentials(vn_persona):
        summary.skipped.append(
            f"{_label_or_id(vn_persona)}: credentials missing — 베트남 페어 불가, 전체 중단"
        )
        return summary

    # 5. 페르소나별 1 세션 생성 (시나리오 N개 합성, Phase F-B).
    scenario_names_str = " + ".join(s.name for s in scenarios)
    for kr_persona in kr_personas:
        kr_label = _label_or_id(kr_persona)
        if not _has_credentials(kr_persona):
            summary.skipped.append(f"{kr_label}: credentials missing")
            continue

        try:
            session_id = await _create_one_pair_combined_session(
                db,
                scenarios=scenarios,
                kr_persona=kr_persona,
                vn_persona=vn_persona,
                bl_ctx=bl_ctx,
            )
            summary.sessions_created.append(session_id)
            logger.info(
                "distribution.weekly: session=%s pair=%s↔%s scenarios=%s 생성(합성)",
                session_id,
                kr_label,
                vn_persona.account_label,
                scenario_names_str,
            )
        except GenerationError as exc:
            msg = f"{kr_label} / 합성({scenario_names_str}): {exc}"
            summary.errors.append(msg)
            logger.warning("distribution.weekly: 생성 실패 — %s", msg)
        except Exception as exc:  # noqa: BLE001 — 페르소나 단위 격리
            msg = (
                f"{kr_label} / 합성({scenario_names_str}): "
                f"예기치 못한 오류 ({type(exc).__name__})"
            )
            summary.errors.append(msg)
            logger.exception("distribution.weekly: 예외 — %s", msg)

    # 6. 한 번에 커밋 (개별 flush 는 위에서 수행됨, 트랜잭션 완료).
    if summary.sessions_created:
        try:
            await db.commit()
        except Exception:
            logger.exception("distribution.weekly: 커밋 실패 — 롤백")
            await db.rollback()
            summary.errors.append("DB 커밋 실패 — 모든 세션 롤백됨")
            summary.sessions_created.clear()
    else:
        # 아무 것도 만들지 않았다면 롤백으로 정리.
        await db.rollback()

    return summary
