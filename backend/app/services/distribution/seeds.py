"""신사업유통 시드 데이터 (T9 PRD Phase 1~2).

용도:
- 페르소나 2종 (VN-A, KR-A1) 초기 등록.
  자격증명(api_id/hash)은 비워서 등록 — 어드민 UI 에서 직접 입력해야 활성화됨.
- 시나리오 5종 (베트남↔한국 1:1 유통 패턴) 초기 등록.
  ``업무개선요구사항/신사업팀/시나리오 샘플.txt`` 7개월치 대화에서 추출.

실행:
    docker compose exec backend python -m app.services.distribution.seeds

멱등:
- account_label / scenario.name 이 이미 존재하면 INSERT 건너뜀.
- 강제 갱신은 ``--force`` 플래그 (구현은 추후).
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.distribution import DistributionPersona, DistributionScenario

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 페르소나 톤 프로필 — 시나리오 샘플 관찰 기반
# ---------------------------------------------------------------------------

# KR-A1: 한국 측 관리자. 정보 주도형 — 안부 인사 → 정보 분할 송신.
# 샘플 패턴: "안녕하세요~" → "BL/컨테이너" → "도착일" 식으로 1줄씩 분할.
KR_A1_TONE: dict = {
    "formality": 0.4,
    "emoji_freq": 0.08,
    "typo_rate": 0.02,
    "preferred_endings": ["~", "요", "있습니다", "예요"],
    "common_phrases": [
        "안녕하세요~",
        "감사합니다",
        "확인 부탁드립니다",
        "넵",
        "맞습니다",
    ],
    "msg_split": "high",  # 정보 여러 개일 때 짧게 나눠 송신
    "time_active": [9, 11, 14, 17],
}

# KR-A2: 친근/캐주얼 톤. 이모지·줄임말 약간 더 자주.
# 샘플 패턴: "안녕하세용~", "넵넵", "ㅎㅎ" 등 가벼운 표현.
KR_A2_TONE: dict = {
    "formality": 0.25,
    "emoji_freq": 0.18,
    "typo_rate": 0.025,
    "preferred_endings": ["~", "요", "용", "어요", "네요", "ㅎㅎ"],
    "common_phrases": [
        "안녕하세용~",
        "넵넵",
        "ㅎㅎ",
        "그쵸",
        "감사해용",
        "확인했어요",
    ],
    "msg_split": "high",
    "time_active": [10, 12, 15, 18],
}

# KR-A3: 조심/정중 톤. 격식 높고 이모지 거의 없음.
# 샘플 패턴: "안녕하십니까", "확인 부탁드립니다", "감사합니다."
KR_A3_TONE: dict = {
    "formality": 0.85,
    "emoji_freq": 0.0,
    "typo_rate": 0.005,
    "preferred_endings": ["습니다", "입니다", "드립니다", "있습니다"],
    "common_phrases": [
        "안녕하십니까",
        "확인 부탁드립니다",
        "감사합니다",
        "수고하셨습니다",
        "검토 후 회신드리겠습니다",
    ],
    "msg_split": "medium",
    "time_active": [9, 11, 14, 16],
}

# KR-A4: 효율 위주. 짧은 메시지·단답형, 메시지 분할 적음.
# 샘플 패턴: "넵", "확인", "ok", "공유해주세요" 위주.
KR_A4_TONE: dict = {
    "formality": 0.35,
    "emoji_freq": 0.02,
    "typo_rate": 0.015,
    "preferred_endings": ["요", "다", "넵", "확인"],
    "common_phrases": [
        "넵",
        "확인",
        "ok",
        "공유 부탁",
        "전달 완료",
        "확인했습니다",
    ],
    "msg_split": "low",
    "time_active": [9, 13, 17],
}

# VN-A: 베트남 창고(중국) 측. 더 단정·짧은 응답.
# 샘플 패턴: "넵 알겠습니다", "받았습니다", "감사합니다" 위주.
VN_A_TONE: dict = {
    "formality": 0.5,
    "emoji_freq": 0.05,
    "typo_rate": 0.01,
    "preferred_endings": ["~", "있습니다", "알겠습니다"],
    "common_phrases": [
        "넵",
        "알겠습니다",
        "받았습니다",
        "감사합니다",
        "확인했습니다",
    ],
    "msg_split": "medium",
    "time_active": [10, 12, 15, 18],  # 베트남 현지 시각 가정 (KST -2h 라 약간 늦음)
}


PERSONA_SEEDS: list[dict] = [
    {
        "account_label": "KR-A1",
        "role": "domestic_admin",
        "display_name": "한국 관리자 A1",
        "telegram_phone": "+820000000000",  # 실 등록 시 어드민 UI 에서 갱신
        "tone_profile": KR_A1_TONE,
        "daily_msg_limit": 30,
    },
    {
        "account_label": "KR-A2",
        "role": "domestic_admin",
        "display_name": "한국 관리자 A2",
        "telegram_phone": "+820000000002",
        "tone_profile": KR_A2_TONE,
        "daily_msg_limit": 30,
    },
    {
        "account_label": "KR-A3",
        "role": "domestic_admin",
        "display_name": "한국 관리자 A3",
        "telegram_phone": "+820000000003",
        "tone_profile": KR_A3_TONE,
        "daily_msg_limit": 30,
    },
    {
        "account_label": "KR-A4",
        "role": "domestic_admin",
        "display_name": "한국 관리자 A4",
        "telegram_phone": "+820000000004",
        "tone_profile": KR_A4_TONE,
        "daily_msg_limit": 30,
    },
    {
        "account_label": "VN-A",
        "role": "vietnam_admin",
        "display_name": "베트남 창고",
        "telegram_phone": "+840000000000",
        "tone_profile": VN_A_TONE,
        "daily_msg_limit": 30,
    },
]


# ---------------------------------------------------------------------------
# 시나리오 5종 — 시나리오 샘플.txt 에서 추출
# ---------------------------------------------------------------------------


SCENARIO_SEEDS: list[dict] = [
    {
        "name": "정기 출고 여부 확인",
        "trigger_event": "inventory_check",
        "sender_role": "vietnam_admin",
        "receiver_role": "domestic_admin",
        "beats": [
            {"step": 1, "intent": "베트남 측이 이번달 출고 여부 질문 (안부 없이 본론)", "tone_hint": "짧게"},
            {"step": 2, "intent": "한국 측이 출고 가능/불가 응답", "tone_hint": "단정"},
            {"step": 3, "intent": "베트남이 알겠다고 답변", "tone_hint": None},
            {"step": 4, "intent": "베트남이 현재 준비 중인 제품 종류 추가 질문 (선택)", "tone_hint": None},
            {"step": 5, "intent": "한국이 제품 종류 답변", "tone_hint": None},
            {"step": 6, "intent": "베트남이 준비되면 알려달라고 마무리", "tone_hint": "친근"},
        ],
        "example_msgs": [
            {"sender": "VN-A", "content": "지난번에 물건 보낸다는거 이번에 물건 보내나요?"},
            {"sender": "KR-A1", "content": "아직 준비가 안되어서 이번에는 못보낼거같아요"},
            {"sender": "VN-A", "content": "알겠습니다."},
            {"sender": "VN-A", "content": "현재 준비하고 계신 제품은 어떤 제품들이 있을까요?"},
            {"sender": "KR-A1", "content": "대부분 가방 BAG 많이 있습니다."},
            {"sender": "VN-A", "content": "준비되시면 연락주세요~"},
        ],
        "raw_text": "[샘플 2026-01-06 발췌 · 2026-05-26 안부 인사 제거]",
    },
    {
        "name": "출고 알림 + 수량",
        "trigger_event": "shipment_notice",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "beats": [
            {"step": 1, "intent": "한국 측이 금일 물건 보낸다고 알림 (안부 없이 본론)", "tone_hint": None},
            {"step": 2, "intent": "수량과 품목 분리 송신", "tone_hint": "분할"},
            {"step": 3, "intent": "베트남이 받겠다고 응답", "tone_hint": "단정"},
            {"step": 4, "intent": "한국이 현재 재고 수량 추가 알림", "tone_hint": None},
            {"step": 5, "intent": "베트남이 확인 응답하며 마무리", "tone_hint": None},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "금일 물건 가방 BAG 28개 준비해서 물류사 통해서 물건 보내겠습니다."},
            {"sender": "VN-A", "content": "넵 알겠습니다. 물건 받고 연락드리겠습니다."},
            {"sender": "KR-A1", "content": "그러면 현재 재고는 249개 입니다."},
            {"sender": "VN-A", "content": "넵 알겠습니다."},
        ],
        "raw_text": "[샘플 2026-05-04 발췌 · 2026-05-26 안부 인사 제거]",
    },
    {
        "name": "도착 확인 + 재고 업데이트",
        "trigger_event": "arrival_confirm",
        "sender_role": "vietnam_admin",
        "receiver_role": "domestic_admin",
        "beats": [
            {"step": 1, "intent": "베트남이 받은 수량 보고 (안부 없이 본론)", "tone_hint": None},
            {"step": 2, "intent": "감사 표현", "tone_hint": None},
            {"step": 3, "intent": "한국이 감사 응답 + 현재 재고 합계 알림", "tone_hint": None},
            {"step": 4, "intent": "베트남이 확인 응답", "tone_hint": "단정"},
        ],
        "example_msgs": [
            {"sender": "VN-A", "content": "보내주신 28개 BAG 잘 받았습니다. 감사합니다."},
            {"sender": "KR-A1", "content": "그러면 현재 재고는 277개입니다."},
            {"sender": "VN-A", "content": "넵 확인했습니다."},
        ],
        "raw_text": "[샘플 2026-05-07 발췌 · 2026-05-26 안부 인사 제거]",
    },
    {
        "name": "주문 처리 (재고 차감)",
        "trigger_event": "order_processing",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "beats": [
            {"step": 1, "intent": "한국이 현지 바이어 주문 수량 알림 (안부 없이 본론)", "tone_hint": None},
            {"step": 2, "intent": "베트남이 알겠다고 + 오늘 물건 가져간다고 전달받았다고 응답", "tone_hint": None},
            {"step": 3, "intent": "한국이 남는 재고 수량 확인 질문", "tone_hint": None},
            {"step": 4, "intent": "베트남이 재고 수량 확인 응답", "tone_hint": None},
            {"step": 5, "intent": "한국이 감사 표현하며 마무리", "tone_hint": None},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "현지 바이어에서 주문 들어왔습니다. 총 256개 제품 주문 들어왔습니다."},
            {"sender": "VN-A", "content": "넵. 연락 받았습니다. 오늘 물건 가져간다고 전달 받았습니다."},
            {"sender": "KR-A1", "content": "그러면 현재 남아 있는 재고는 221개가 맞나요?"},
            {"sender": "VN-A", "content": "넵 맞습니다."},
            {"sender": "KR-A1", "content": "감사합니다."},
        ],
        "raw_text": "[샘플 2026-04-03 발췌 · 2026-05-26 안부 인사 제거]",
    },
    {
        "name": "지연 안내 (연휴/물류)",
        "trigger_event": "delay",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "beats": [
            {"step": 1, "intent": "한국이 연휴/물류 사정으로 다음달 출고 가능성 안내 (안부 없이 본론)", "tone_hint": "정중"},
            {"step": 2, "intent": "베트남이 이해 + 자기 측 연휴 일정 공유 + 다른 업체도 비슷한 상황 언급", "tone_hint": "공감"},
            {"step": 3, "intent": "한국이 동의 + 준비해서 보내겠다고 답변", "tone_hint": None},
            {"step": 4, "intent": "베트남이 현재 한국 재고 수량 추가 질문 (선택)", "tone_hint": None},
            {"step": 5, "intent": "한국이 재고 수량 답변", "tone_hint": None},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "이번달 한국 명절하고, 물류사 일정이 떄문에 다음달에 보내야 할수도 있습니다."},
            {"sender": "VN-A", "content": "넵. 저도 이야기 들었습니다. 저희도 2월 14일부터 2월 22일까지 연휴이기 떄문에 다른 회사들도 모두 물류 문제가 있다고 이야기 들었습니다."},
            {"sender": "KR-A1", "content": "맞습니다. 물류 준비해서 보내겠습니다."},
            {"sender": "VN-A", "content": "현재 한국에는 재고가 대략 몇 개 정도 있을까요?"},
            {"sender": "KR-A1", "content": "477개"},
        ],
        "raw_text": "[샘플 2026-02-13 발췌 · 2026-05-26 안부 인사 제거]",
    },
    # -----------------------------------------------------------------------
    # B-2 신규 시나리오 — 종합관리시트 주간 + 명품재고대장 연동 (0518 요구사항)
    # -----------------------------------------------------------------------
    {
        "name": "주간 정산 요약",
        "trigger_event": "weekly_settlement",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "beats": [
            {"step": 1, "intent": "지난주 매입 금액 공유 + 입금요청 안내(40%) (안부 없이 본론)", "tone_hint": "분할"},
            {"step": 2, "intent": "재고이동 금액 공유 + 30% 입금요청 추가 안내", "tone_hint": "정보 분할"},
            {"step": 3, "intent": "매출완료 금액 확인 질문", "tone_hint": "정중"},
            {"step": 4, "intent": "베트남이 숫자 확인 응답", "tone_hint": "단정"},
            {"step": 5, "intent": "한국이 계좌입금/현금캐리 수령 확인 + 감사 표현", "tone_hint": "마무리"},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "지난주 매입 {kr_purchase}원 입니다, 입금 {kr_purchase_deposit_req}원 부탁드립니다."},
            {"sender": "KR-A1", "content": "재고이동은 {vn_inventory_move}원 이니까 입금 {vn_inventory_deposit_req}원 추가입니다."},
            {"sender": "KR-A1", "content": "매출 확정 {vn_sales_completed}원이라고 주셨는데 이상 없으시죠?"},
            {"sender": "VN-A", "content": "넵 숫자 맞습니다."},
            {"sender": "VN-A", "content": "확인했습니다."},
            {"sender": "KR-A1", "content": "계좌 입금이랑, 현금캐리 잘 받았습니다. 감사합니다."},
        ],
        "raw_text": "[0518 요구사항 · 2026-05-26 안부 인사 제거]",
    },
    {
        "name": "명품 추가 매입 요청",
        "trigger_event": "product_request",
        "sender_role": "vietnam_admin",
        "receiver_role": "domestic_admin",
        "beats": [
            {"step": 1, "intent": "베트남이 이번주 명품 재고 확인했다는 본론으로 시작 (안부 없이)", "tone_hint": None},
            {"step": 2, "intent": "베스트 브랜드/제품 언급 (루이비통/고야드/반클리프/Cartier 등)", "tone_hint": "정보"},
            {"step": 3, "intent": "이 제품들 무한으로 오더 가능하다고 전달", "tone_hint": "단정"},
            {"step": 4, "intent": "특정 카테고리 추가 확보 가능 여부 질문 (가방/주얼리 등)", "tone_hint": None},
            {"step": 5, "intent": "한국이 다음주 입고 확인 후 전달하겠다고 응답", "tone_hint": "정중"},
        ],
        "example_msgs": [
            {"sender": "VN-A", "content": "이번주 명품 재고 확인했습니다."},
            {"sender": "VN-A", "content": "루이비통, 반클리프, 고야드 베스트 제품들 숫자 무한으로 오더드립니다."},
            {"sender": "VN-A", "content": "특히 가방류 더 확보 가능할까요?"},
            {"sender": "KR-A1", "content": "넵 다음주 입고 분 확인해서 전달드리겠습니다."},
            {"sender": "KR-A1", "content": "브랜드별 수량은 정리해서 다시 공유드릴게요."},
        ],
        "raw_text": "[0518 요구사항 · 2026-05-26 안부 인사 제거]",
    },
    # 가벼운 스몰토크 시나리오는 2026-05-26 사용자 결정으로 제거.
    # ---------------------------------------------------------------------------
    # 분기 VIP 프로모션 — 재고 소진 (2026-05-26 신규)
    # ---------------------------------------------------------------------------
    {
        "name": "분기 VIP 프로모션 (재고 소진)",
        "trigger_event": "vip_promotion_quarterly",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "attachment_required": True,
        "beats": [
            {"step": 1, "intent": "분기 VIP 프로모션 일정 안내 (안부 없이 본론, 숫자 직접 노출 X)", "tone_hint": "정중"},
            {"step": 2, "intent": "대상 품목 카테고리만 텍스트로 언급 (구체 수량/가격은 첨부 엑셀 참조 안내)", "tone_hint": None},
            {"step": 3, "intent": "엑셀 파일에 품목/수량/적용가가 정리되어 있다고 첨부 가이드", "tone_hint": "단정"},
            {"step": 4, "intent": "VIP 고객 접수 마감일·진행 방식 안내", "tone_hint": None},
            {"step": 5, "intent": "베트남이 확인 + 현지 VIP 의향 회신 일정 제안", "tone_hint": None},
            {"step": 6, "intent": "한국이 회신 일정 동의 + 추가 문의는 별도 답신 부탁한다고 마무리", "tone_hint": "마무리"},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "이번 분기 VIP 프로모션 시작합니다. 잔여 재고 일부를 VIP 한정으로 풀게요."},
            {"sender": "KR-A1", "content": "대상은 가방·소가죽·주얼리 카테고리 위주입니다. 브랜드 라인업은 같이 보낸 엑셀에 정리되어 있어요."},
            {"sender": "KR-A1", "content": "품목·수량·적용가는 첨부 파일 참고 부탁드립니다. 텔레그램 메시지로는 숫자 따로 안 보내요."},
            {"sender": "KR-A1", "content": "VIP 회신 마감은 다음주 금요일까지로 잡았습니다."},
            {"sender": "VN-A", "content": "확인했습니다. 엑셀 보고 현지 VIP에 안내한 다음 이번주 안에 회신드릴게요."},
            {"sender": "KR-A1", "content": "넵 좋습니다. 추가 문의 있으시면 따로 답신 부탁드려요."},
        ],
        "raw_text": "[2026-05-26 신규 — VIP 프로모션, 숫자는 엑셀 첨부 전달]",
    },
]


async def seed_personas(session: AsyncSession) -> int:
    """페르소나 시드 등록. 이미 존재하는 account_label 은 건너뜀."""
    inserted = 0
    for data in PERSONA_SEEDS:
        existing = await session.execute(
            select(DistributionPersona).where(
                DistributionPersona.account_label == data["account_label"]
            )
        )
        if existing.scalar_one_or_none() is not None:
            logger.info("페르소나 %s 이미 존재 — 건너뜀", data["account_label"])
            continue
        persona = DistributionPersona(**data)
        session.add(persona)
        inserted += 1
    if inserted:
        await session.commit()
    logger.info("페르소나 신규 등록: %d 건", inserted)
    return inserted


async def seed_scenarios(session: AsyncSession) -> int:
    """시나리오 시드 등록. 이미 존재하는 name 은 건너뜀."""
    inserted = 0
    for data in SCENARIO_SEEDS:
        existing = await session.execute(
            select(DistributionScenario).where(
                DistributionScenario.name == data["name"]
            )
        )
        if existing.scalar_one_or_none() is not None:
            logger.info("시나리오 %s 이미 존재 — 건너뜀", data["name"])
            continue
        scenario = DistributionScenario(**data)
        session.add(scenario)
        inserted += 1
    if inserted:
        await session.commit()
    logger.info("시나리오 신규 등록: %d 건", inserted)
    return inserted


async def seed_all() -> None:
    """전체 시드 실행."""
    async with async_session() as session:
        p_count = await seed_personas(session)
        s_count = await seed_scenarios(session)
    logger.info("시드 완료: 페르소나 %d, 시나리오 %d", p_count, s_count)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(seed_all())


if __name__ == "__main__":
    main()
