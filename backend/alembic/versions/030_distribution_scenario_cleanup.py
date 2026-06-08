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

시나리오 정의는 seeds.py 를 단일 출처로 import (중복 정의 방지).

Revision ID: 030
Revises: 029
Create Date: 2026-06-08
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

from app.services.distribution.seeds import (
    DEACTIVATED_SCENARIO_NAMES,
    NEW_DELIVERY_SCENARIOS,
)

revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


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
    for sc in NEW_DELIVERY_SCENARIOS:
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
                "beats": json.dumps(sc.get("beats", []), ensure_ascii=False),
                "example_msgs": json.dumps(
                    sc.get("example_msgs"), ensure_ascii=False
                ),
                "raw_text": sc.get("raw_text"),
                "language": sc.get("language", "ko"),
                "attachment_required": bool(sc.get("attachment_required", False)),
            },
        )

    # 2) 불필요 시나리오 비활성 (picker 숨김). 삭제 아님 — 기존 세션 보존.
    if DEACTIVATED_SCENARIO_NAMES:
        stmt = sa.text(
            "UPDATE distribution_scenarios SET active = FALSE WHERE name IN :names"
        ).bindparams(sa.bindparam("names", expanding=True))
        bind.execute(stmt, {"names": list(DEACTIVATED_SCENARIO_NAMES)})

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
    if DEACTIVATED_SCENARIO_NAMES:
        stmt = sa.text(
            "UPDATE distribution_scenarios SET active = TRUE WHERE name IN :names"
        ).bindparams(sa.bindparam("names", expanding=True))
        bind.execute(stmt, {"names": list(DEACTIVATED_SCENARIO_NAMES)})

    # 1) 신규 시나리오 제거 (business_name 복구는 비가역 — 다운그레이드 미지원).
    names = [sc["name"] for sc in NEW_DELIVERY_SCENARIOS]
    if names:
        stmt = sa.text(
            "DELETE FROM distribution_scenarios WHERE name IN :names"
        ).bindparams(sa.bindparam("names", expanding=True))
        bind.execute(stmt, {"names": names})
