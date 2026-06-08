"""T9 신사업유통 시나리오 정리 + 김준기 페르소나 라벨 자동화 (2026-06-08).

작업 (시나리오 추가.txt 요구사항 반영):
1. 신규 시나리오 3종 추가 (하자·장기재고 / 명품주문~대금회수 / 주문~정산).
   - 공급 방향 고정: 한국=공급/매입/발송, 베트남=주문/수령/현지판매.
   - 이미 같은 name 이 있으면 건너뜀(멱등).
2. 불필요 시나리오 비활성(active=False) — picker 에서 숨김.
   - "지연 안내 (연휴/물류)" + zh 미러. 세션 FK(RESTRICT) 보존 위해 삭제 대신 비활성.
3. 김준기 페르소나 라벨 자동화: 수동으로 박혀 있던 business_name("TK101(김준기계정)")
   을 NULL 로 비워, picker 라벨이 연동 텔레그램 계정의 라이브 display_name 으로
   자동 표기되도록 전환. (login/sync 시 display_name 자동 갱신 — login_manager)

주의: 이 파일은 컨테이너 기동 시(alembic upgrade head) 자동 실행되므로,
가변적인 app 코드(seeds 등)를 import 하지 않고 데이터를 인라인으로 보관한다
(마이그레이션 = 시점 스냅샷, 자기완결형).

Revision ID: 030
Revises: 029
Create Date: 2026-06-08
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


# 신규 시나리오 3종 (한국=공급/매입, 베트남=주문/수령 방향 고정).
NEW_SCENARIOS: list[dict] = [
    {
        "name": "물품 하자·장기재고 관리 협의",
        "trigger_event": "defect_inventory_mgmt",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "beats": [
            {"step": 1, "intent": "한국이 현지에서 접수된 일부 품목 하자 건 처리 진행 상황 안내 (안부 없이 본론, 메일성 정중 톤)", "tone_hint": "정중"},
            {"step": 2, "intent": "장기 미판매(장기재고) 품목 현황 정리해서 회신 요청", "tone_hint": "정중"},
            {"step": 3, "intent": "베트남이 하자 수량·사진과 장기재고 리스트 회신", "tone_hint": "단정"},
            {"step": 4, "intent": "한국이 교환/반품·재고 소진(프로모션 등) 처리 방침 안내 + 기록 보관 언급", "tone_hint": "정보 분할"},
            {"step": 5, "intent": "베트남이 확인 + 진행 동의", "tone_hint": None},
            {"step": 6, "intent": "한국이 이번 협의 내용 정리해 남기겠다고 마무리(증빙용)", "tone_hint": "마무리"},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "지난번 접수된 하자 건 처리 진행 상황 공유드립니다."},
            {"sender": "KR-A1", "content": "장기 미판매로 남아있는 품목들도 현황 한번 정리해서 보내주실 수 있을까요?"},
            {"sender": "VN-A", "content": "넵. 하자 3건 사진하고 장기재고 리스트 정리해서 보내드리겠습니다."},
            {"sender": "KR-A1", "content": "하자분은 교환 처리하고, 장기재고는 프로모션으로 소진하는 방향으로 진행하겠습니다."},
            {"sender": "KR-A1", "content": "처리 내역은 기록으로 남겨두겠습니다."},
            {"sender": "VN-A", "content": "넵 확인했습니다. 그렇게 진행 부탁드립니다."},
        ],
        "raw_text": "[시나리오 추가.txt ① 하자·장기재고 관리 · 2026-06-08]",
        "language": "ko",
        "attachment_required": False,
    },
    {
        "name": "명품 주문~에어 수출~대금 회수",
        "trigger_event": "luxury_order_to_settlement",
        "sender_role": "vietnam_admin",
        "receiver_role": "domestic_admin",
        "beats": [
            {"step": 1, "intent": "베트남이 명품 주문 발주 (브랜드·수량) (안부 없이 본론)", "tone_hint": None},
            {"step": 2, "intent": "한국이 접수 + 국내에서 해당 명품 매입 진행한다고 안내", "tone_hint": "단정"},
            {"step": 3, "intent": "한국이 인천 창고 집결 후 에어(항공) 수출 일정 안내", "tone_hint": "정보 분할"},
            {"step": 4, "intent": "베트남이 수령 예정 확인", "tone_hint": None},
            {"step": 5, "intent": "한국이 수출대금 회수(결제) 일정·방식 안내", "tone_hint": "정중"},
            {"step": 6, "intent": "베트남이 입금/정산 확인하며 마무리", "tone_hint": "마무리"},
        ],
        "example_msgs": [
            {"sender": "VN-A", "content": "이번에 루이비통, 고야드 위주로 주문드립니다. 수량은 정리해서 보냈어요."},
            {"sender": "KR-A1", "content": "넵 접수했습니다. 국내에서 해당 제품 매입 바로 진행하겠습니다."},
            {"sender": "KR-A1", "content": "인천 창고에 모아서 에어로 수출 보내겠습니다. 출고되면 일정 공유드릴게요."},
            {"sender": "VN-A", "content": "넵 도착하면 수령 확인드리겠습니다."},
            {"sender": "KR-A1", "content": "수출대금은 도착 확인 후 정산으로 부탁드립니다."},
            {"sender": "VN-A", "content": "넵 입금 처리하고 정산 내역 보내드리겠습니다."},
        ],
        "raw_text": "[시나리오 추가.txt ② 명품 주문~에어수출~대금회수 · 2026-06-08]",
        "language": "ko",
        "attachment_required": False,
    },
    {
        "name": "주문~입금확인~1차배송~정산",
        "trigger_event": "order_payment_settlement",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "beats": [
            {"step": 1, "intent": "한국이 단톡방으로 들어온 주문 접수 확인 (안부 없이 본론)", "tone_hint": None},
            {"step": 2, "intent": "자금 입금 확인 (위챗으로 선물영수증 확인 후 등록 완료 언급)", "tone_hint": "단정"},
            {"step": 3, "intent": "한국이 물품 수령 후 베트남으로 1차 배송 진행 안내", "tone_hint": "정보 분할"},
            {"step": 4, "intent": "베트남이 수령 확인", "tone_hint": None},
            {"step": 5, "intent": "한국이 최종 판매 후 정산 + 구글시트 정리하겠다고 안내", "tone_hint": "마무리"},
            {"step": 6, "intent": "베트남이 정산 내역 확인하며 마무리", "tone_hint": None},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "단톡방으로 들어온 주문 접수했습니다."},
            {"sender": "KR-A1", "content": "입금 확인했고, 위챗으로 받은 선물영수증도 등록 완료했습니다."},
            {"sender": "KR-A1", "content": "물건 수령해서 베트남으로 1차 배송 진행하겠습니다."},
            {"sender": "VN-A", "content": "넵 받으면 바로 확인드리겠습니다."},
            {"sender": "KR-A1", "content": "최종 판매되면 정산하고 구글시트에 정리해두겠습니다."},
            {"sender": "VN-A", "content": "넵 정산 내역 확인하겠습니다. 감사합니다."},
        ],
        "raw_text": "[시나리오 추가.txt ③ 주문~입금~1차배송~정산 · 2026-06-08]",
        "language": "ko",
        "attachment_required": False,
    },
]


# picker 에서 비활성(숨김) 처리할 불필요 시나리오 (지연 시나리오 정리).
DEACTIVATED_SCENARIO_NAMES: list[str] = [
    "지연 안내 (연휴/물류)",
    "延迟通知 (假期/物流) (中文)",
]


_INSERT_SQL = sa.text(
    """
    INSERT INTO distribution_scenarios
        (name, trigger_event, sender_role, receiver_role,
         beats, example_msgs, raw_text, language, active, attachment_required)
    VALUES
        (:name, :trigger_event, :sender_role, :receiver_role,
         CAST(:beats AS JSONB), CAST(:example_msgs AS JSONB),
         :raw_text, :language, TRUE, :attachment_required)
    """
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 신규 시나리오 추가 (이미 존재하는 name 은 건너뜀).
    for sc in NEW_SCENARIOS:
        exists = bind.execute(
            sa.text("SELECT 1 FROM distribution_scenarios WHERE name = :n"),
            {"n": sc["name"]},
        ).first()
        if exists is not None:
            continue
        bind.execute(
            _INSERT_SQL,
            {
                "name": sc["name"],
                "trigger_event": sc["trigger_event"],
                "sender_role": sc["sender_role"],
                "receiver_role": sc["receiver_role"],
                "beats": json.dumps(sc["beats"], ensure_ascii=False),
                "example_msgs": json.dumps(sc["example_msgs"], ensure_ascii=False),
                "raw_text": sc["raw_text"],
                "language": sc["language"],
                "attachment_required": sc["attachment_required"],
            },
        )

    # 2) 불필요 시나리오 비활성 (picker 숨김). 삭제 아님 — 기존 세션 보존.
    stmt = sa.text(
        "UPDATE distribution_scenarios SET active = FALSE WHERE name IN :names"
    ).bindparams(sa.bindparam("names", expanding=True))
    bind.execute(stmt, {"names": DEACTIVATED_SCENARIO_NAMES})

    # 3) 김준기 수동 라벨 제거 → 라이브 계정 display_name 으로 자동 표기 전환.
    bind.execute(
        sa.text(
            "UPDATE distribution_personas SET business_name = NULL "
            "WHERE business_name LIKE :pat"
        ),
        {"pat": "%김준기%"},
    )


def downgrade() -> None:
    bind = op.get_bind()

    # 2) 비활성 시나리오 복구.
    stmt = sa.text(
        "UPDATE distribution_scenarios SET active = TRUE WHERE name IN :names"
    ).bindparams(sa.bindparam("names", expanding=True))
    bind.execute(stmt, {"names": DEACTIVATED_SCENARIO_NAMES})

    # 1) 신규 시나리오 제거 (business_name 복구는 비가역 — 미지원).
    names = [sc["name"] for sc in NEW_SCENARIOS]
    stmt = sa.text(
        "DELETE FROM distribution_scenarios WHERE name IN :names"
    ).bindparams(sa.bindparam("names", expanding=True))
    bind.execute(stmt, {"names": names})
