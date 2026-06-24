"""Add distribution Google Docs link confirmation scenario.

Revision ID: 036
Revises: 035
Create Date: 2026-06-24
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


SCENARIOS: list[dict] = [
    {
        "name": "구글 Docs 링크 확인 요청",
        "trigger_event": "docs_link_visibility_check",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "language": "ko",
        "beats": [
            {"step": 1, "intent": "한국이 아래 링크에서 보낸 내용을 볼 수 있는지 확인 요청", "tone_hint": "짧고 정중"},
            {"step": 2, "intent": "한국이 구글 Docs/Sheets 링크를 별도 메시지로 발송", "tone_hint": "링크만 단독 발송"},
            {"step": 3, "intent": "베트남이 받았고 확인해보겠다고 응답", "tone_hint": "단정"},
            {"step": 4, "intent": "한국이 감사 인사 또는 문의 있으면 답변 달라고 안내", "tone_hint": "마무리"},
            {"step": 5, "intent": "베트남이 확인 또는 감사 인사로 마무리", "tone_hint": None},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "안녕하세요~ 아래 링크에서 저희가 보낸 내용 확인 가능하신지 봐주세요."},
            {"sender": "KR-A1", "content": "https://docs.google.com/spreadsheets/d/1k4m6B4jIFFhUIUqrlFARs17ZrvWL66fwh-sojurToZk/edit?gid=1797875960#gid=1797875960"},
            {"sender": "VN-A", "content": "네, 받았습니다. 확인해보겠습니다. 감사합니다."},
            {"sender": "KR-A1", "content": "네 감사합니다."},
        ],
        "raw_text": "[2026-06-24 신규 — 구글 Docs 링크 확인 요청]",
    },
    {
        "name": "Google Docs 链接确认请求 (中文)",
        "trigger_event": "docs_link_visibility_check",
        "sender_role": "domestic_admin",
        "receiver_role": "vietnam_admin",
        "language": "zh",
        "beats": [
            {"step": 1, "intent": "韩国方请对方确认下面链接是否能看到发送内容", "tone_hint": "简短礼貌"},
            {"step": 2, "intent": "韩国方单独发送 Google Docs/Sheets 链接", "tone_hint": "只发链接"},
            {"step": 3, "intent": "越南方回复收到并会看一下", "tone_hint": "自然商务"},
            {"step": 4, "intent": "韩国方表示感谢，或提醒有疑问请回复", "tone_hint": "收尾"},
            {"step": 5, "intent": "越南方用好的/谢谢收尾", "tone_hint": None},
        ],
        "example_msgs": [
            {"sender": "KR-A1", "content": "您好~请帮我们确认一下, 下面的链接，能看到我们发送的内容。"},
            {"sender": "KR-A1", "content": "https://docs.google.com/spreadsheets/d/1k4m6B4jIFFhUIUqrlFARs17ZrvWL66fwh-sojurToZk/edit?gid=1797875960#gid=1797875960"},
            {"sender": "VN-A", "content": "好的，收到，我们看一下。谢谢。"},
            {"sender": "KR-A1", "content": "有什么疑问的话，请回复一下。"},
            {"sender": "VN-A", "content": "好的，谢谢"},
        ],
        "raw_text": "[2026-06-24 신규 — Google Docs 링크 확인 요청 zh 미러]",
    },
]


_INSERT_SQL = sa.text(
    """
    INSERT INTO distribution_scenarios
        (name, trigger_event, sender_role, receiver_role,
         beats, example_msgs, raw_text, language, active, attachment_required)
    VALUES
        (:name, :trigger_event, :sender_role, :receiver_role,
         CAST(:beats AS JSONB), CAST(:example_msgs AS JSONB),
         :raw_text, :language, TRUE, FALSE)
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    for scenario in SCENARIOS:
        exists = bind.execute(
            sa.text("SELECT 1 FROM distribution_scenarios WHERE name = :name"),
            {"name": scenario["name"]},
        ).first()
        if exists is not None:
            continue
        bind.execute(
            _INSERT_SQL,
            {
                "name": scenario["name"],
                "trigger_event": scenario["trigger_event"],
                "sender_role": scenario["sender_role"],
                "receiver_role": scenario["receiver_role"],
                "beats": json.dumps(scenario["beats"], ensure_ascii=False),
                "example_msgs": json.dumps(scenario["example_msgs"], ensure_ascii=False),
                "raw_text": scenario["raw_text"],
                "language": scenario["language"],
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    names = [scenario["name"] for scenario in SCENARIOS]
    stmt = sa.text(
        "DELETE FROM distribution_scenarios WHERE name IN :names"
    ).bindparams(sa.bindparam("names", expanding=True))
    bind.execute(stmt, {"names": names})
