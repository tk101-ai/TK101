"""playground 모듈 — AI Playground (T8 Phase 1) 신규 테이블 3종

목적 (T8 PRD 4·5·7·10):
- playground_sessions: 사용자별 LLM 채팅 세션 메타 (provider/model/system_prompt/temperature).
- playground_messages: 세션별 role 기반 메시지 + 토큰/지연/모델/원본 페이로드 메트릭.
- playground_media: Phase 4~5 미디어 생성 결과 사전 예약 (이미지/영상/오디오 URL + 비용).

설계 메모:
- 모두 신규 빈 테이블이므로 CONCURRENTLY 불필요 (운영 영향 없음).
- raw_request/raw_response 는 JSONB — Authorization 등 시크릿은 라우터 단에서 masked.
- 인덱스:
    * playground_sessions: (user_id, created_at DESC) — 본인 세션 최신순.
    * playground_messages: (session_id, created_at) — 세션 메시지 시간순.
- session/user/message FK 는 CASCADE — 사용자/세션 삭제 시 메시지/미디어도 함께 정리.
- temperature numeric(3,2): 0.00 ~ 2.00 범위. 기본 0.70.

Revision ID: 009
Revises: 008
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------------
    # 1. playground_sessions — 채팅 세션 메타
    # ---------------------------------------------------------------------
    op.create_table(
        "playground_sessions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=True),
        # provider: "claude" | "openai" | "gemini" 등. Phase 1은 claude만.
        sa.Column("provider", sa.String(50), nullable=False),
        # model: 정확한 모델 ID (예: claude-haiku-4-5-20251001).
        sa.Column("model", sa.String(100), nullable=False),
        sa.Column("system_prompt", sa.Text, nullable=True),
        sa.Column(
            "temperature",
            sa.Numeric(3, 2),
            nullable=False,
            server_default=sa.text("0.70"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
    )
    # 본인 세션 최신순 조회용. DESC 정렬 인덱스 (PG 9.x+ 지원).
    op.create_index(
        "ix_playground_sessions_user_created",
        "playground_sessions",
        ["user_id", sa.text("created_at DESC")],
    )

    # ---------------------------------------------------------------------
    # 2. playground_messages — 메시지 + 메트릭
    # ---------------------------------------------------------------------
    op.create_table(
        "playground_messages",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("playground_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # role: "user" | "assistant" | "system" (system 은 보통 세션 단위라 드물게 사용).
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        # 토큰/지연 메트릭 — assistant 메시지에만 채워짐, user 는 NULL.
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("reasoning_tokens", sa.Integer, nullable=True),
        sa.Column("cached_tokens", sa.Integer, nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        # raw_request: 시크릿 마스킹된 요청 페이로드. raw_response: 마지막 stream chunk 또는 final usage.
        sa.Column("raw_request", JSONB, nullable=True),
        sa.Column("raw_response", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_playground_messages_session_created",
        "playground_messages",
        ["session_id", "created_at"],
    )

    # ---------------------------------------------------------------------
    # 3. playground_media — Phase 4~5 미리 준비 (이미지/영상/오디오)
    # ---------------------------------------------------------------------
    op.create_table(
        "playground_media",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("playground_sessions.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # media_type: "image" | "video" | "audio".
        sa.Column("media_type", sa.String(20), nullable=False),
        sa.Column("prompt", sa.Text, nullable=True),
        sa.Column("url", sa.String, nullable=False),
        sa.Column("duration_sec", sa.Numeric(8, 2), nullable=True),
        sa.Column("width", sa.Integer, nullable=True),
        sa.Column("height", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # 역순 — 의존성: media/messages → sessions.
    op.drop_table("playground_media")
    op.drop_index(
        "ix_playground_messages_session_created",
        table_name="playground_messages",
    )
    op.drop_table("playground_messages")
    op.drop_index(
        "ix_playground_sessions_user_created",
        table_name="playground_sessions",
    )
    op.drop_table("playground_sessions")
