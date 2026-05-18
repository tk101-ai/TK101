"""distribution 모듈 — 신사업유통 텔레그램 대화 자동화 (T9 PRD).

목적 (T9 PRD 5절):
- distribution_personas: 텔레그램 운영 계정 (베트남/국내 관리자) + 톤 프로필.
- distribution_bl_records: 엑셀에서 적재한 BL/면장 행.
- distribution_scenarios: 시나리오 템플릿 (트리거 이벤트 + 비트 + few-shot 예시).
- distribution_sessions: Claude 가 생성한 대화 세션 (검수 게이트).
- distribution_messages: 세션 내 개별 메시지 + 송신 메타.
- distribution_send_log: 송신 시도 결과 (감사 + BAN 디버깅).

설계 메모:
- 1차 라이브는 VN-A + KR-A1 2계정 1:1. 가번호 3개는 추후 UI 등록만으로 합류.
- api_id/api_hash 는 *_enc 컬럼에 Fernet 암호화 저장 (T9 PRD 7-1). 평문 저장 금지.
- session 은 status='approved' 일 때만 송신 워커가 픽업 → 검수 누락 헛소리 송신 방지.
- send_log 는 BAN/FLOOD_WAIT 사유 추적용. 회전·만료 시 운영자가 즉시 대응.

인덱스:
- distribution_sessions: (status, generated_at DESC) — 검수 대기 큐 최신순.
- distribution_messages: partial index (status='queued', scheduled_at) — 송신 워커 폴링.
- distribution_send_log: (persona_id, attempted_at DESC) — 페르소나별 실패율 모니터링.

Revision ID: 010
Revises: 009
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ---------------------------------------------------------------------
    # 1. distribution_personas — 텔레그램 운영 계정
    # ---------------------------------------------------------------------
    op.create_table(
        "distribution_personas",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # account_label: "VN-A", "KR-A1" 등 사람이 식별하는 코드명. UI 표시에도 사용.
        sa.Column("account_label", sa.String(20), nullable=False, unique=True),
        # role: "vietnam_admin" | "domestic_admin". 시나리오 매칭에 사용.
        sa.Column("role", sa.String(30), nullable=False),
        # display_name: 텔레그램에서 보이는 이름.
        sa.Column("display_name", sa.String(100), nullable=False),
        # telegram_phone: +84... / +82-10-... 형식. 1계정당 1번호.
        sa.Column("telegram_phone", sa.String(30), nullable=False, unique=True),
        # telegram_user_id: Telethon 첫 로그인 후 자동 채움 (참조용).
        sa.Column("telegram_user_id", sa.BigInteger, nullable=True, unique=True),
        # api_id_enc / api_hash_enc: Fernet 암호화 저장. 평문 DB 노출 금지.
        sa.Column("api_id_enc", sa.Text, nullable=True),
        sa.Column("api_hash_enc", sa.Text, nullable=True),
        # session_path: Telethon .session 파일 절대 경로. 권한 0600 강제.
        sa.Column("session_path", sa.String(500), nullable=True),
        # tone_profile: {formality, emoji_freq, typo_rate, common_phrases, ...}
        sa.Column("tone_profile", JSONB, nullable=True),
        # daily_msg_limit: rate limit 가드. 워밍업 기간엔 낮게 설정.
        sa.Column(
            "daily_msg_limit",
            sa.Integer,
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        # warmup_until: 이 날짜 이전엔 송신 빈도 낮춤 (BAN 방지).
        sa.Column("warmup_until", sa.Date, nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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

    # ---------------------------------------------------------------------
    # 2. distribution_bl_records — 엑셀 BL/면장 적재
    # ---------------------------------------------------------------------
    op.create_table(
        "distribution_bl_records",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("bl_number", sa.String(100), nullable=True),
        sa.Column("container_no", sa.String(50), nullable=True),
        sa.Column("product", sa.String(200), nullable=True),
        sa.Column("quantity", sa.Integer, nullable=True),
        sa.Column("departure_date", sa.Date, nullable=True),
        sa.Column("arrival_date", sa.Date, nullable=True),
        sa.Column("destination", sa.String(100), nullable=True),
        # raw_row: 엑셀 원본 행 (컬럼명→값) — 매핑 후에도 원본 보존.
        sa.Column("raw_row", JSONB, nullable=True),
        sa.Column("source_file", sa.String(255), nullable=True),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "imported_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # 같은 BL+컨테이너 조합 중복 적재 방지.
        sa.UniqueConstraint(
            "bl_number", "container_no", name="uq_distribution_bl_records_bl_container"
        ),
    )

    # ---------------------------------------------------------------------
    # 3. distribution_scenarios — 시나리오 템플릿
    # ---------------------------------------------------------------------
    op.create_table(
        "distribution_scenarios",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(100), nullable=False),
        # trigger_event: shipment_notice / arrival_eta / customs_clear / delay / arrival_confirm 등.
        sa.Column("trigger_event", sa.String(50), nullable=False),
        # sender/receiver role: persona.role 과 매칭. 동일 role 페르소나 풀에서 자동 선택 가능.
        sa.Column("sender_role", sa.String(30), nullable=False),
        sa.Column("receiver_role", sa.String(30), nullable=False),
        # beats: [{step, intent, tone_hint}] — Claude 프롬프트에 주입.
        sa.Column("beats", JSONB, nullable=False),
        # raw_text: 사용자 원본 시나리오 .md (감사용).
        sa.Column("raw_text", sa.Text, nullable=True),
        # example_msgs: 사용자 제공 few-shot 예시. AI 티 제거 핵심.
        sa.Column("example_msgs", JSONB, nullable=True),
        sa.Column(
            "active",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # ---------------------------------------------------------------------
    # 4. distribution_sessions — Claude 생성 대화 세션 (검수 게이트)
    # ---------------------------------------------------------------------
    op.create_table(
        "distribution_sessions",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # bl_record_id: BL 기반 트리거인 경우. 수동 트리거는 NULL 허용.
        sa.Column(
            "bl_record_id",
            UUID(as_uuid=True),
            sa.ForeignKey("distribution_bl_records.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "scenario_id",
            UUID(as_uuid=True),
            sa.ForeignKey("distribution_scenarios.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "sender_persona_id",
            UUID(as_uuid=True),
            sa.ForeignKey("distribution_personas.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "receiver_persona_id",
            UUID(as_uuid=True),
            sa.ForeignKey("distribution_personas.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # status: pending / approved / rejected / sending / sent / failed.
        # 송신 워커는 'approved' 만 픽업.
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "approved_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # scheduled_start: 첫 메시지 송신 예정 시각. status='approved' 시 워커가 사용.
        sa.Column("scheduled_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # LLM 비용/토큰 메트릭 (Langfuse 연계).
        sa.Column("llm_cost_usd", sa.Numeric(10, 6), nullable=True),
        sa.Column("llm_input_tok", sa.Integer, nullable=True),
        sa.Column("llm_output_tok", sa.Integer, nullable=True),
    )
    op.create_index(
        "ix_distribution_sessions_status_generated",
        "distribution_sessions",
        ["status", sa.text("generated_at DESC")],
    )

    # ---------------------------------------------------------------------
    # 5. distribution_messages — 개별 메시지
    # ---------------------------------------------------------------------
    op.create_table(
        "distribution_messages",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            UUID(as_uuid=True),
            sa.ForeignKey("distribution_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("order_index", sa.Integer, nullable=False),
        sa.Column(
            "sender_persona_id",
            UUID(as_uuid=True),
            sa.ForeignKey("distribution_personas.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        # content: LLM 생성 원본. edited_content 가 있으면 그게 우선 송신.
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("edited_content", sa.Text, nullable=True),
        sa.Column(
            "user_edited",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        # send_after_sec: 이전 메시지 송신 후 N초 뒤 (자연스러운 시간차).
        sa.Column("send_after_sec", sa.Integer, nullable=False),
        # typing_sec: 타이핑 인디케이터 노출 시간 (글자 수에 비례).
        sa.Column(
            "typing_sec",
            sa.Integer,
            nullable=False,
            server_default=sa.text("3"),
        ),
        # status: queued / sent / failed / skipped.
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default=sa.text("'queued'"),
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        # telegram_message_id: 송신 성공 시 Telethon 이 반환하는 메시지 ID.
        sa.Column("telegram_message_id", sa.String(50), nullable=True),
    )
    # 송신 워커가 큐 폴링하는 partial index. status='queued' 행만 인덱스에 포함.
    op.create_index(
        "ix_distribution_messages_queue",
        "distribution_messages",
        ["scheduled_at"],
        postgresql_where=sa.text("status = 'queued'"),
    )

    # ---------------------------------------------------------------------
    # 6. distribution_send_log — 송신 시도 로그
    # ---------------------------------------------------------------------
    op.create_table(
        "distribution_send_log",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "message_id",
            UUID(as_uuid=True),
            sa.ForeignKey("distribution_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "persona_id",
            UUID(as_uuid=True),
            sa.ForeignKey("distribution_personas.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "attempt",
            sa.Integer,
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("success", sa.Boolean, nullable=True),
        # error_code: FLOOD_WAIT / AUTH_KEY_UNREGISTERED / PEER_FLOOD / ... (Telethon enum).
        sa.Column("error_code", sa.String(50), nullable=True),
        sa.Column("error_detail", sa.Text, nullable=True),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_distribution_send_log_persona_attempted",
        "distribution_send_log",
        ["persona_id", sa.text("attempted_at DESC")],
    )


def downgrade() -> None:
    # 역순 — 의존성: send_log/messages → sessions → bl_records/scenarios/personas.
    op.drop_index(
        "ix_distribution_send_log_persona_attempted",
        table_name="distribution_send_log",
    )
    op.drop_table("distribution_send_log")
    op.drop_index(
        "ix_distribution_messages_queue",
        table_name="distribution_messages",
    )
    op.drop_table("distribution_messages")
    op.drop_index(
        "ix_distribution_sessions_status_generated",
        table_name="distribution_sessions",
    )
    op.drop_table("distribution_sessions")
    op.drop_table("distribution_scenarios")
    op.drop_table("distribution_bl_records")
    op.drop_table("distribution_personas")
