"""신사업유통 텔레그램 대화 자동화 모델 (T9 PRD).

설계:
- personas: 텔레그램 운영 계정. api_id/hash 는 *_enc 컬럼에 Fernet 암호화로 저장.
- bl_records: 엑셀 BL/면장 적재 결과. raw_row 로 원본 보존.
- scenarios: 시나리오 템플릿. beats + example_msgs 가 Claude 프롬프트에 주입됨.
- sessions: Claude 생성 대화 세션. status='approved' 일 때만 송신 워커 픽업.
- messages: 세션 내 메시지. edited_content 가 있으면 우선 송신.
- send_log: 송신 시도 결과 (BAN/FLOOD_WAIT 추적).

기존 패턴 (playground.py, account.py) 과 동일하게 ``Column(...)`` 스타일.
SQLAlchemy 2.0 typed (Mapped) 은 base.py 일부만 사용 중이라 일관성 유지를 위해 column 기반.
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base


class DistributionPersona(Base):
    """텔레그램 운영 계정 1개.

    api_id_enc / api_hash_enc 는 Fernet 암호화 평문 base64 토큰.
    어드민 UI 에서 평문 입력 → 즉시 암호화 후 저장 → 화면엔 마스킹만 노출.
    """

    __tablename__ = "distribution_personas"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # account_label: 사람이 식별하는 코드명 (VN-A, KR-A1 등). UI 표시에도 사용.
    account_label = Column(String(20), nullable=False, unique=True)
    # role: "vietnam_admin" | "domestic_admin". 시나리오 매칭에 사용.
    role = Column(String(30), nullable=False)
    display_name = Column(String(100), nullable=False)
    telegram_phone = Column(String(30), nullable=False, unique=True)
    # telegram_user_id: Telethon 첫 로그인 후 자동 채움.
    telegram_user_id = Column(BigInteger, nullable=True, unique=True)
    # api_id/hash: Fernet 암호화 저장. 평문 DB 노출 금지.
    api_id_enc = Column(Text, nullable=True)
    api_hash_enc = Column(Text, nullable=True)
    # business_name: UI 표시용 사업자명 (예: "주식회사 XYZ"). NULL 이면 display_name 폴백.
    # account_label 은 코드명·라우팅용으로 불변 유지.
    business_name = Column(String(200), nullable=True)
    # session_path: Telethon .session 파일 절대 경로. 권한 0600 강제.
    session_path = Column(String(500), nullable=True)
    # tone_profile: 페르소나별 톤. AI 티 제거의 핵심.
    tone_profile = Column(JSONB, nullable=True)
    daily_msg_limit = Column(Integer, nullable=False, server_default=text("30"))
    active = Column(Boolean, nullable=False, server_default=text("true"))
    # warmup_until: 워밍업 종료일. 이전엔 송신 빈도 낮춤.
    warmup_until = Column(Date, nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=True
    )


class DistributionBlRecord(Base):
    """엑셀 BL/면장 적재 결과 1행.

    raw_row 에 원본 컬럼명-값 매핑 그대로 보존. 양식 변경 시 재처리 가능.
    UNIQUE(bl_number, container_no) 로 중복 적재 차단.
    """

    __tablename__ = "distribution_bl_records"
    __table_args__ = (
        UniqueConstraint(
            "bl_number",
            "container_no",
            name="uq_distribution_bl_records_bl_container",
        ),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    bl_number = Column(String(100), nullable=True)
    container_no = Column(String(50), nullable=True)
    product = Column(String(200), nullable=True)
    quantity = Column(Integer, nullable=True)
    departure_date = Column(Date, nullable=True)
    arrival_date = Column(Date, nullable=True)
    destination = Column(String(100), nullable=True)
    raw_row = Column(JSONB, nullable=True)
    source_file = Column(String(255), nullable=True)
    imported_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    imported_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class DistributionScenario(Base):
    """시나리오 템플릿 1개.

    beats: [{step, intent, tone_hint}] 리스트가 Claude 프롬프트에 주입됨.
    example_msgs: 사용자 제공 few-shot. AI 티 제거의 핵심.
    """

    __tablename__ = "distribution_scenarios"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    name = Column(String(100), nullable=False)
    # trigger_event: shipment_notice / arrival_eta / customs_clear / delay / arrival_confirm / inventory_check.
    trigger_event = Column(String(50), nullable=False)
    sender_role = Column(String(30), nullable=False)
    receiver_role = Column(String(30), nullable=False)
    beats = Column(JSONB, nullable=False)
    raw_text = Column(Text, nullable=True)
    example_msgs = Column(JSONB, nullable=True)
    active = Column(Boolean, nullable=False, server_default=text("true"))
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DistributionSession(Base):
    """Claude 생성 대화 세션 1개. 검수 게이트.

    status='approved' 일 때만 송신 워커가 picks up.
    DB 제약은 아니고 워커 쿼리 단의 필터링 — 어드민이 강제 차단 시엔 inactive 처리.
    """

    __tablename__ = "distribution_sessions"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    # bl_record_id: BL 기반 트리거인 경우. 수동 트리거는 NULL.
    bl_record_id = Column(
        UUID(as_uuid=True),
        ForeignKey("distribution_bl_records.id", ondelete="SET NULL"),
        nullable=True,
    )
    scenario_id = Column(
        UUID(as_uuid=True),
        ForeignKey("distribution_scenarios.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sender_persona_id = Column(
        UUID(as_uuid=True),
        ForeignKey("distribution_personas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    receiver_persona_id = Column(
        UUID(as_uuid=True),
        ForeignKey("distribution_personas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # status: pending / approved / rejected / sending / sent / failed.
    status = Column(String(20), nullable=False, server_default=text("'pending'"))
    approved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    approved_at = Column(DateTime(timezone=True), nullable=True)
    generated_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    scheduled_start = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    # LLM 비용/토큰 메트릭 (Langfuse 연계).
    llm_cost_usd = Column(Numeric(10, 6), nullable=True)
    llm_input_tok = Column(Integer, nullable=True)
    llm_output_tok = Column(Integer, nullable=True)


class DistributionMessage(Base):
    """세션 내 개별 메시지.

    content: LLM 생성 원본. edited_content 가 있으면 우선 송신.
    send_after_sec: 이전 메시지 송신 후 N초 뒤 (자연스러운 시간차).
    """

    __tablename__ = "distribution_messages"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("distribution_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    order_index = Column(Integer, nullable=False)
    sender_persona_id = Column(
        UUID(as_uuid=True),
        ForeignKey("distribution_personas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    content = Column(Text, nullable=False)
    edited_content = Column(Text, nullable=True)
    user_edited = Column(Boolean, nullable=False, server_default=text("false"))
    send_after_sec = Column(Integer, nullable=False)
    typing_sec = Column(Integer, nullable=False, server_default=text("3"))
    # status: queued / sent / failed / skipped.
    status = Column(String(20), nullable=False, server_default=text("'queued'"))
    scheduled_at = Column(DateTime(timezone=True), nullable=True)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    telegram_message_id = Column(String(50), nullable=True)


class DistributionWeeklySummary(Base):
    """주차별 종합 데이터 (래더엑스 종합관리시트 1주차 = 1행).

    company_label + period_start + period_end UNIQUE.
    UPSERT 시 raw_row 갱신 + 자동계산 필드 재계산 가능.
    """

    __tablename__ = "distribution_weekly_summary"
    __table_args__ = (
        UniqueConstraint(
            "company_label",
            "period_start",
            "period_end",
            name="uq_distribution_weekly_summary_period",
        ),
    )

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    company_label = Column(String(100), nullable=False)
    period_label = Column(String(30), nullable=False)
    period_start = Column(Date, nullable=False)
    period_end = Column(Date, nullable=False)
    # 사람 기입
    kr_purchase = Column(Numeric(15, 2), nullable=True)
    vn_inventory_move = Column(Numeric(15, 2), nullable=True)
    vn_sales_completed = Column(Numeric(15, 2), nullable=True)
    # 자동 계산
    kr_purchase_deposit_req = Column(Numeric(15, 2), nullable=True)
    vn_inventory_deposit_req = Column(Numeric(15, 2), nullable=True)
    vn_sales_deposit_req = Column(Numeric(15, 2), nullable=True)
    # 입금 결과
    account_deposit = Column(Numeric(15, 2), nullable=True)
    cash_deposit = Column(Numeric(15, 2), nullable=True)
    raw_row = Column(JSONB, nullable=True)
    source_file = Column(String(255), nullable=True)
    imported_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    imported_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class DistributionProduct(Base):
    """명품재고대장 1행. 브랜드·제품 코드·카테고리·재고 보관.

    매주 풀 갱신 가정 (UPSERT 또는 wipe+insert). 변동 이력 추적은 v0.3.
    매입 대화 시 brand/category 기반 "더 확보" 자동 멘션에 사용.
    """

    __tablename__ = "distribution_products"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    brand = Column(String(100), nullable=False)
    product_name_en = Column(String(500), nullable=True)
    product_code = Column(String(100), nullable=True)
    category = Column(String(50), nullable=True)
    purchase_qty = Column(Integer, nullable=True)
    domestic_stock_qty = Column(Integer, nullable=True)
    supply_price = Column(Numeric(15, 2), nullable=True)
    vat = Column(Numeric(15, 2), nullable=True)
    purchase_price = Column(Numeric(15, 2), nullable=True)
    approval_number = Column(String(50), nullable=True)
    purchase_date = Column(Date, nullable=True)
    raw_row = Column(JSONB, nullable=True)
    source_file = Column(String(255), nullable=True)
    imported_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    imported_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class DistributionSendLog(Base):
    """송신 시도 로그. BAN/FLOOD_WAIT 추적 + 페르소나 실패율 모니터링."""

    __tablename__ = "distribution_send_log"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    message_id = Column(
        UUID(as_uuid=True),
        ForeignKey("distribution_messages.id", ondelete="CASCADE"),
        nullable=False,
    )
    persona_id = Column(
        UUID(as_uuid=True),
        ForeignKey("distribution_personas.id", ondelete="RESTRICT"),
        nullable=False,
    )
    attempt = Column(Integer, nullable=False, server_default=text("1"))
    success = Column(Boolean, nullable=True)
    # error_code: FLOOD_WAIT / AUTH_KEY_UNREGISTERED / PEER_FLOOD / ...
    error_code = Column(String(50), nullable=True)
    error_detail = Column(Text, nullable=True)
    attempted_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
