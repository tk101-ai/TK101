"""신사업유통 시드 데이터 (T9 PRD Phase 1~2).

용도:
- 페르소나 2종 (VN-A, KR-A1) 초기 등록.
  자격증명(api_id/hash)은 비워서 등록 — 어드민 UI 에서 직접 입력해야 활성화됨.
- 시나리오 한국어 8종 + 중국어(간체) 7종 (베트남↔한국 1:1 유통 패턴) 초기 등록.
  ``업무개선요구사항/신사업팀/시나리오 샘플.txt`` 7개월치 대화에서 추출.
  중국어 시나리오는 동일 업무 흐름을 중국 현지 채팅체로 미러링 (T9 — 2026-05-27).

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


# ---------------------------------------------------------------------------
# 중국어(간체) 톤 프로필 — zh 시나리오용. 중국 현지인의 자연스러운 채팅 습관 반영.
# 위 한국어 톤과 1:1 대응하되, 어조 표현만 중국어 채팅 습관으로 치환.
# ---------------------------------------------------------------------------

# KR-A1(중문): 한국 측 관리자. 정보 주도형, 간결하지만 친절.
KR_A1_TONE_ZH: dict = {
    "formality": 0.4,
    "emoji_freq": 0.08,
    "typo_rate": 0.02,
    "preferred_endings": ["哈", "哦", "了", "的"],
    "common_phrases": ["好的", "收到", "麻烦确认一下", "嗯", "对的"],
    "msg_split": "high",
    "time_active": [9, 11, 14, 17],
}

# VN-A(중문): 베트남 창고(중국) 측. 단정·짧은 응답.
VN_A_TONE_ZH: dict = {
    "formality": 0.5,
    "emoji_freq": 0.05,
    "typo_rate": 0.01,
    "preferred_endings": ["了", "的", "哈"],
    "common_phrases": ["好", "明白", "收到了", "谢谢", "确认过了"],
    "msg_split": "medium",
    "time_active": [10, 12, 15, 18],
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
            {"step": 2, "intent": "수량과 품목 분리 송신 (가방 BAG N개, 물류사 경유)", "tone_hint": "분할"},
            {"step": 3, "intent": "베트남이 받겠다고 + 도착하면 연락드리겠다고 응답", "tone_hint": "단정"},
            {"step": 4, "intent": "한국이 누적 재고 산식 알림 (기존 재고 + 금일 출고 = 합계)", "tone_hint": "분할"},
            {"step": 5, "intent": "베트남이 확인 응답하며 마무리", "tone_hint": None},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "금일 물건 가방 BAG 28개 준비해서 물류사 통해서 보내겠습니다."},
            {"sender": "VN-A", "content": "넵 알겠습니다. 물건 받고 연락드리겠습니다."},
            {"sender": "KR-A1", "content": "현재 재고 상황은 기존 창고 249개 + 금일 48개 = 297개 입니다."},
            {"sender": "VN-A", "content": "넵 알겠습니다."},
        ],
        "raw_text": "[샘플 2026-05-04·05-11 발췌 · 2026-05-26 안부 인사 제거]",
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


# ---------------------------------------------------------------------------
# 중국어(간체) 시나리오 — 한국어 5종 업무 흐름을 그대로 미러링 (T9 — 2026-05-27)
# 출고확인 / 출고알림+수량 / 도착+재고 / 주문처리 / 지연안내 / VIP프로모션.
# example_msgs 는 중국 현지인 채팅체 few-shot. 명품 브랜드·수량은 한국어판과 동일 맥락.
# name 은 한국어판과 충돌하지 않도록 "(中文)" 접미어로 구분.
# ---------------------------------------------------------------------------

SCENARIO_SEEDS_ZH: list[dict] = [
    {
        "name": "定期出货确认 (中文)",
        "trigger_event": "inventory_check",
        "sender_role": "vietnam_admin",
        "receiver_role": "domestic_admin",
        "language": "zh",
        "beats": [
            {"step": 1, "intent": "越南仓直接问这个月发不发货(不寒暄)", "tone_hint": "简短"},
            {"step": 2, "intent": "韩国方回复能发/暂时发不了", "tone_hint": "干脆"},
            {"step": 3, "intent": "越南仓回个'好的'", "tone_hint": None},
            {"step": 4, "intent": "越南仓追问现在备的是哪些品类", "tone_hint": None},
            {"step": 5, "intent": "韩国方回答主要是哪类货(如包BAG)", "tone_hint": None},
            {"step": 6, "intent": "越南仓说备好了通知一声收尾", "tone_hint": "随和"},
        ],
        "example_msgs": [
            {"sender": "VN-A", "content": "上次说要发的货，这个月发吗？"},
            {"sender": "KR-A1", "content": "还没备齐，这次可能发不了"},
            {"sender": "VN-A", "content": "好的"},
            {"sender": "VN-A", "content": "现在在备的都是哪些品类呀？"},
            {"sender": "KR-A1", "content": "大部分是包 BAG 比较多"},
            {"sender": "VN-A", "content": "行，备好了通知我一声哈"},
        ],
        "raw_text": "[샘플 2026-01-06 기반 zh 미러 · 2026-05-27]",
    },
    {
        "name": "出货通知+数量 (中文)",
        "trigger_event": "shipment_notice",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "language": "zh",
        "beats": [
            {"step": 1, "intent": "韩国方说今天发货(不寒暄直接进正题)", "tone_hint": None},
            {"step": 2, "intent": "拆开发数量和品类(包 BAG N件, 走物流公司)", "tone_hint": "拆分"},
            {"step": 3, "intent": "越南仓说收到、到货了通知", "tone_hint": "干脆"},
            {"step": 4, "intent": "韩国方报累计库存算式(原库存+今日出货=合计)", "tone_hint": "拆分"},
            {"step": 5, "intent": "越南仓确认收尾", "tone_hint": None},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "今天备了包 BAG 28件，走物流公司发过去"},
            {"sender": "VN-A", "content": "好的，到货了我通知你"},
            {"sender": "KR-A1", "content": "现在库存是 原仓249件 + 今天48件 = 297件"},
            {"sender": "VN-A", "content": "明白了"},
        ],
        "raw_text": "[샘플 2026-05-04·05-11 기반 zh 미러 · 2026-05-27]",
    },
    {
        "name": "到货确认+库存更新 (中文)",
        "trigger_event": "arrival_confirm",
        "sender_role": "vietnam_admin",
        "receiver_role": "domestic_admin",
        "language": "zh",
        "beats": [
            {"step": 1, "intent": "越南仓报收到的数量(不寒暄)", "tone_hint": None},
            {"step": 2, "intent": "道个谢", "tone_hint": None},
            {"step": 3, "intent": "韩国方回谢+报当前库存合计", "tone_hint": None},
            {"step": 4, "intent": "越南仓确认", "tone_hint": "干脆"},
        ],
        "example_msgs": [
            {"sender": "VN-A", "content": "发来的 28件 BAG 收到了，谢谢"},
            {"sender": "KR-A1", "content": "好的，那现在库存是 277件"},
            {"sender": "VN-A", "content": "确认过了"},
        ],
        "raw_text": "[샘플 2026-05-07 기반 zh 미러 · 2026-05-27]",
    },
    {
        "name": "订单处理 (库存扣减) (中文)",
        "trigger_event": "order_processing",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "language": "zh",
        "beats": [
            {"step": 1, "intent": "韩国方说当地买家下单数量(不寒暄)", "tone_hint": None},
            {"step": 2, "intent": "越南仓说收到、今天去提货已通知到", "tone_hint": None},
            {"step": 3, "intent": "韩国方核对剩余库存数", "tone_hint": None},
            {"step": 4, "intent": "越南仓确认库存数", "tone_hint": None},
            {"step": 5, "intent": "韩国方道谢收尾", "tone_hint": None},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "当地买家下单了，一共 256件"},
            {"sender": "VN-A", "content": "好的，接到通知了，今天去提货那边也说了"},
            {"sender": "KR-A1", "content": "那现在剩的库存是 221件 对吧？"},
            {"sender": "VN-A", "content": "对的"},
            {"sender": "KR-A1", "content": "谢谢哈"},
        ],
        "raw_text": "[샘플 2026-04-03 기반 zh 미러 · 2026-05-27]",
    },
    {
        "name": "延迟通知 (假期/物流) (中文)",
        "trigger_event": "delay",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "language": "zh",
        "beats": [
            {"step": 1, "intent": "韩国方说因假期/物流档期, 可能要下个月才发(不寒暄)", "tone_hint": "客气"},
            {"step": 2, "intent": "越南仓表示理解+说自己这边假期安排+别家也都这样", "tone_hint": "共情"},
            {"step": 3, "intent": "韩国方同意+说会备好就发", "tone_hint": None},
            {"step": 4, "intent": "越南仓追问韩国现在大概多少库存", "tone_hint": None},
            {"step": 5, "intent": "韩国方报库存数", "tone_hint": None},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "这个月赶上韩国节假日，加上物流公司档期，可能得下个月才能发"},
            {"sender": "VN-A", "content": "嗯，我也听说了。我们这边 2月14到22号 也放假，别家公司也都说物流有点卡"},
            {"sender": "KR-A1", "content": "对的，我备好物流就发"},
            {"sender": "VN-A", "content": "现在韩国那边大概还有多少库存呀？"},
            {"sender": "KR-A1", "content": "477件"},
        ],
        "raw_text": "[샘플 2026-02-13 기반 zh 미러 · 2026-05-27]",
    },
    {
        "name": "名品追加采购请求 (中文)",
        "trigger_event": "product_request",
        "sender_role": "vietnam_admin",
        "receiver_role": "domestic_admin",
        "language": "zh",
        "beats": [
            {"step": 1, "intent": "越南仓说这周名品库存看过了(不寒暄)", "tone_hint": None},
            {"step": 2, "intent": "点名最好卖的品牌/款(LV/Goyard/梵克雅宝/Cartier 等)", "tone_hint": "给信息"},
            {"step": 3, "intent": "说这些款可以无限量下单", "tone_hint": "干脆"},
            {"step": 4, "intent": "问某个品类(包/珠宝)能不能多备点", "tone_hint": None},
            {"step": 5, "intent": "韩国方说下周到货确认后再给", "tone_hint": "客气"},
        ],
        "example_msgs": [
            {"sender": "VN-A", "content": "这周名品库存我看过了"},
            {"sender": "VN-A", "content": "LV、梵克雅宝、Goyard 这几个爆款可以无限量下单"},
            {"sender": "VN-A", "content": "尤其是包类能不能多备点？"},
            {"sender": "KR-A1", "content": "好的，下周到货那批确认一下再发你"},
            {"sender": "KR-A1", "content": "各品牌数量我整理好再发一遍哈"},
        ],
        "raw_text": "[0518 요구사항 기반 zh 미러 · 2026-05-27]",
    },
    {
        "name": "季度VIP促销 (清库存) (中文)",
        "trigger_event": "vip_promotion_quarterly",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "language": "zh",
        "attachment_required": True,
        "beats": [
            {"step": 1, "intent": "通知季度VIP促销安排(不寒暄, 不直接报数字)", "tone_hint": "客气"},
            {"step": 2, "intent": "只用文字提对象品类(具体数量/价格看附件Excel)", "tone_hint": None},
            {"step": 3, "intent": "引导看附件: 品类/数量/促销价都整理在Excel里", "tone_hint": "干脆"},
            {"step": 4, "intent": "说明VIP接单截止日和流程", "tone_hint": None},
            {"step": 5, "intent": "越南仓确认+提出回复当地VIP意向的时间", "tone_hint": None},
            {"step": 6, "intent": "韩国方同意时间+有问题另外回信收尾", "tone_hint": "收尾"},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "这个季度的 VIP 促销开始了，一部分余货限 VIP 放出来"},
            {"sender": "KR-A1", "content": "对象主要是包、小皮具、珠宝这几类。品牌清单我整理在一起发的 Excel 里了"},
            {"sender": "KR-A1", "content": "品类、数量、促销价都看附件哈，数字我不在消息里单独发"},
            {"sender": "KR-A1", "content": "VIP 回复截止定在下周五"},
            {"sender": "VN-A", "content": "收到，我看完 Excel 通知当地 VIP，这周内回你"},
            {"sender": "KR-A1", "content": "好的，有别的问题再单独回信哈"},
        ],
        "raw_text": "[2026-05-26 VIP 프로모션 zh 미러 · 2026-05-27]",
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
    """시나리오 시드 등록 (한국어 + 중국어). 이미 존재하는 name 은 건너뜀.

    language 미지정 dict 는 'ko' 로 보정 (한국어 시드).
    """
    inserted = 0
    for data in (*SCENARIO_SEEDS, *SCENARIO_SEEDS_ZH):
        existing = await session.execute(
            select(DistributionScenario).where(
                DistributionScenario.name == data["name"]
            )
        )
        if existing.scalar_one_or_none() is not None:
            logger.info("시나리오 %s 이미 존재 — 건너뜀", data["name"])
            continue
        # language 기본값 보정 (한국어 시드는 컬럼 미지정).
        row = {**data, "language": data.get("language", "ko")}
        scenario = DistributionScenario(**row)
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
