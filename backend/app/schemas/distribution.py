"""신사업유통 텔레그램 자동화 Pydantic 스키마 (T9 PRD).

엔드포인트 매핑 (Day 2~5 구현):
- /api/distribution/personas              → PersonaCreate / PersonaOut / PersonaUpdate
- /api/distribution/personas/{id}/login   → PersonaLoginInit / PersonaLoginInitResult
- /api/distribution/personas/{id}/verify  → PersonaVerifyCode
- /api/distribution/scenarios             → ScenarioCreate / ScenarioOut
- /api/distribution/bl/upload             → BlUploadResult
- /api/distribution/generate              → GenerateRequest / GenerateResult
- /api/distribution/sessions              → DistributionSessionOut
- /api/distribution/messages/{id}         → MessageEditRequest / DistributionMessageOut

규칙:
- api_id/api_hash 평문 입력은 PersonaCreate 에서만 받고, 응답은 항상 마스킹된 값만 노출.
- tone_profile / beats / example_msgs 는 JSONB → dict/list 로 받음. 스키마는 dict 로 느슨하게.
- DB 응답 모델은 ``model_config = {"from_attributes": True}`` 로 ORM 변환.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Persona — 텔레그램 운영 계정
# ---------------------------------------------------------------------------

# role 열거 — DB 컬럼은 String 이지만 API 단에서 enum 강제.
PersonaRole = Literal["vietnam_admin", "domestic_admin"]


class PersonaCreate(BaseModel):
    """새 페르소나 등록 요청 (어드민 UI 폼).

    api_id / api_hash 는 평문 입력 → 라우터에서 즉시 Fernet 암호화 → DB 저장.
    저장 후 응답에는 절대 평문이 포함되지 않음 (PersonaOut 참조).

    account_label 은 Telethon .session 파일명으로 직접 사용되므로
    path traversal 방지를 위해 alphanumeric + 하이픈/언더스코어만 허용.
    """

    account_label: str = Field(
        min_length=1,
        max_length=20,
        pattern=r"^[A-Za-z0-9_-]+$",
        description="예: VN-A. 영문/숫자/하이픈/언더스코어만 허용",
    )
    role: PersonaRole
    display_name: str = Field(min_length=1, max_length=100)
    telegram_phone: str = Field(
        min_length=5,
        max_length=30,
        description="국가코드 포함. 예: +84901234567 / +821012345678",
    )
    # 평문 입력 — 라우터에서 encrypt() 후 DB 저장. 응답에 포함 X.
    api_id: str = Field(min_length=1, max_length=20, description="my.telegram.org 발급 숫자")
    api_hash: str = Field(min_length=32, max_length=32, description="32자 hex")
    tone_profile: dict | None = None
    daily_msg_limit: int = Field(default=30, ge=1, le=1000)
    warmup_days: int = Field(default=7, ge=0, le=30, description="이 일수만큼 워밍업 기간 설정")


class PersonaUpdate(BaseModel):
    """페르소나 부분 수정. api_id/api_hash 재입력은 별도 흐름 (보안)."""

    # account_label(라벨/코드명) 수정 가능 (2026-06-08 요청).
    # .session 파일명에 쓰이므로 path traversal 방지 위해 영문/숫자/하이픈/언더스코어만.
    # UNIQUE — 중복 시 라우터에서 409. 이미 로그인된 계정은 stored session_path 를
    # 그대로 사용하므로 라벨을 바꿔도 기존 세션은 유지됨(파일명만 옛 라벨로 남음).
    account_label: str | None = Field(
        default=None,
        min_length=1,
        max_length=20,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    display_name: str | None = Field(default=None, max_length=100)
    # business_name: 사업자명 라벨 (UI 표시 우선). account_label 코드명과 별개.
    business_name: str | None = Field(default=None, max_length=200)
    tone_profile: dict | None = None
    daily_msg_limit: int | None = Field(default=None, ge=1, le=1000)
    active: bool | None = None
    warmup_until: date | None = None


class PersonaCredentialsUpdate(BaseModel):
    """자격증명 갱신 요청 (UI '자격증명 입력' 모달).

    용도:
    - 시드된 placeholder (+820000000000 등) 페르소나에 실 자격증명 주입.
    - 기존 페르소나의 api_id/api_hash 회전.

    동작:
    - phone / api_id / api_hash 모두 필수.
    - Fernet 으로 즉시 재암호화 후 DB 저장 (PersonaCreate 와 동일 패턴).
    - 기존 Telethon 세션은 자격증명과 불일치 가능하므로 안전을 위해 무효화 (재로그인 필요).
    """

    telegram_phone: str = Field(
        min_length=5,
        max_length=30,
        description="국가코드 포함. 예: +821012345678",
    )
    api_id: str = Field(
        min_length=1,
        max_length=20,
        description="my.telegram.org 발급 숫자",
    )
    api_hash: str = Field(
        min_length=32,
        max_length=32,
        description="32자 hex",
    )


class PersonaOut(BaseModel):
    """페르소나 조회 응답. 평문 자격증명 절대 노출 X."""

    id: uuid.UUID
    account_label: str
    role: PersonaRole
    display_name: str
    business_name: str | None = None
    telegram_phone: str
    telegram_user_id: int | None
    # telegram_username: 연동된 텔레그램 계정 @username (로그인/수동 동기화 시 자동).
    telegram_username: str | None = None
    # 자격증명 등록 여부만 노출 (실 값 X).
    has_credentials: bool
    # session 파일 존재 여부 (Telethon 로그인 완료 여부).
    is_logged_in: bool
    tone_profile: dict | None
    daily_msg_limit: int
    active: bool
    warmup_until: date | None
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Telethon 로그인 흐름 (Day 4)
# ---------------------------------------------------------------------------


class PersonaLoginInit(BaseModel):
    """SMS 코드 발송 요청. body 없음 — persona_id 는 path."""


class PersonaLoginInitResult(BaseModel):
    """SMS 발송 완료 응답.

    phone_code_hash 는 Telethon 이 반환하는 임시 토큰. verify 시 같이 보내야 함.
    """

    phone_code_hash: str
    sent_to: str = Field(description="발송된 폰번호 (마스킹)")


class PersonaVerifyCode(BaseModel):
    """SMS 코드 검증 요청."""

    phone_code_hash: str = Field(description="login_init 응답에서 받은 토큰")
    code: str = Field(min_length=4, max_length=10, description="SMS 받은 코드")
    # 2FA 활성화된 계정용 비밀번호. 평문 입력 후 세션 생성에만 사용, DB 저장 X.
    password: str | None = Field(default=None, max_length=200)


# ---------------------------------------------------------------------------
# Scenario — 시나리오 템플릿
# ---------------------------------------------------------------------------

# trigger_event 열거. Day 2 시점 5종, 추가는 v0.2.0.
TriggerEvent = Literal[
    "shipment_notice",  # 출고 알림
    "arrival_eta",  # 도착 예정
    "customs_clear",  # 통관 완료
    "delay",  # 지연 안내
    "arrival_confirm",  # 도착 확인 + 재고
    "inventory_check",  # 정기 안부 + 재고 확인
    "order_processing",  # 주문 처리 (재고 차감)
]


class ScenarioBeat(BaseModel):
    """대화 비트 1단계 — 시나리오 진행의 마디.

    step: 1부터 시작하는 순서.
    intent: "안부 인사", "BL 번호 공유", "재고 확인" 같은 행동.
    tone_hint: "친근하게", "사과 톤" 같은 어조 힌트.
    """

    step: int = Field(ge=1)
    intent: str = Field(min_length=1, max_length=500)
    tone_hint: str | None = Field(default=None, max_length=200)


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    trigger_event: TriggerEvent
    sender_role: PersonaRole
    receiver_role: PersonaRole
    beats: list[ScenarioBeat] = Field(min_length=1, max_length=20)
    raw_text: str | None = Field(default=None, max_length=20_000)
    example_msgs: list[dict] | None = Field(
        default=None,
        description="few-shot 예시. 각 항목: {sender, content}",
    )


class ScenarioOut(BaseModel):
    id: uuid.UUID
    name: str
    trigger_event: str
    sender_role: str
    receiver_role: str
    beats: list[dict]
    raw_text: str | None
    example_msgs: list[dict] | None
    instruction: str | None = None
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# BL Record — 엑셀 적재 결과
# ---------------------------------------------------------------------------


class BlRecordOut(BaseModel):
    id: uuid.UUID
    bl_number: str | None
    container_no: str | None
    product: str | None
    quantity: int | None
    departure_date: date | None
    arrival_date: date | None
    destination: str | None
    source_file: str | None
    imported_at: datetime

    model_config = {"from_attributes": True}


class BlUploadResult(BaseModel):
    """엑셀 업로드 결과 요약."""

    inserted: int
    skipped_duplicate: int
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Generation — 대화 생성 트리거
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    """대화 생성 트리거 (수동 또는 n8n cron).

    옵션:
    - bl_record_ids 명시 → 해당 BL 들에 대해 생성.
    - 빈 리스트 + auto_pick=True → status='pending' 인 신규 BL 자동 매칭.
    """

    bl_record_ids: list[uuid.UUID] = Field(default_factory=list)
    scenario_id: uuid.UUID | None = Field(
        default=None,
        description="명시하지 않으면 trigger_event 자동 매칭",
    )
    sender_persona_id: uuid.UUID | None = None
    receiver_persona_id: uuid.UUID | None = None
    auto_pick: bool = Field(
        default=False,
        description="True 면 신규 BL + 활성 페르소나 자동 선택",
    )


class GenerateResult(BaseModel):
    """생성 응답."""

    session_ids: list[uuid.UUID]
    skipped: int = 0
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Session / Message — 검수 화면
# ---------------------------------------------------------------------------


SessionStatus = Literal[
    "pending", "approved", "rejected", "sending", "sent", "failed"
]


class DistributionMessageOut(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    order_index: int
    sender_persona_id: uuid.UUID
    content: str
    edited_content: str | None
    user_edited: bool
    send_after_sec: int
    typing_sec: int
    status: str
    scheduled_at: datetime | None
    sent_at: datetime | None
    telegram_message_id: str | None

    model_config = {"from_attributes": True}


class DistributionSessionOut(BaseModel):
    id: uuid.UUID
    bl_record_id: uuid.UUID | None
    scenario_id: uuid.UUID
    sender_persona_id: uuid.UUID
    receiver_persona_id: uuid.UUID
    status: SessionStatus
    approved_by: uuid.UUID | None
    approved_at: datetime | None
    generated_at: datetime
    scheduled_start: datetime | None
    completed_at: datetime | None
    llm_cost_usd: Decimal | None
    llm_input_tok: int | None
    llm_output_tok: int | None

    model_config = {"from_attributes": True}


class DistributionSessionDetail(BaseModel):
    """세션 상세 (검수 화면 main view)."""

    session: DistributionSessionOut
    messages: list[DistributionMessageOut]


class MessageEditRequest(BaseModel):
    """메시지 인라인 편집."""

    edited_content: str = Field(min_length=1, max_length=4096)


class SessionApprovalRequest(BaseModel):
    """검수 승인. 송신 시작 시각 지정 가능 (없으면 즉시)."""

    scheduled_start: datetime | None = None


class SessionRejectRequest(BaseModel):
    """재생성 트리거. 다른 시나리오/페르소나로 바꿀 수 있음."""

    reason: str | None = Field(default=None, max_length=500)
    new_scenario_id: uuid.UUID | None = None
    new_sender_persona_id: uuid.UUID | None = None
    new_receiver_persona_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# Send Log
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Weekly Summary / Products (Phase B-1)
# ---------------------------------------------------------------------------


class WeeklySummaryOut(BaseModel):
    """주차별 종합 데이터 1행 (래더엑스 종합관리시트)."""

    id: uuid.UUID
    company_label: str
    period_label: str
    period_start: date
    period_end: date
    kr_purchase: Decimal | None
    vn_inventory_move: Decimal | None
    vn_sales_completed: Decimal | None
    kr_purchase_deposit_req: Decimal | None
    vn_inventory_deposit_req: Decimal | None
    vn_sales_deposit_req: Decimal | None
    account_deposit: Decimal | None
    cash_deposit: Decimal | None
    source_file: str | None
    imported_at: datetime

    model_config = {"from_attributes": True}


class ProductOut(BaseModel):
    """명품재고대장 1행."""

    id: uuid.UUID
    # company_label: 4개 회사 분리 (T9 Phase F-A). 구 데이터는 None 가능 (백필 전).
    company_label: str | None = None
    brand: str
    product_name_en: str | None
    product_code: str | None
    category: str | None
    purchase_qty: int | None
    domestic_stock_qty: int | None
    # VN(베트남) 수량 — 시트 col 19/21/22. 과거 행은 None.
    vn_inventory_move_qty: int | None = None
    vn_sales_completed_qty: int | None = None
    vn_local_stock_qty: int | None = None
    supply_price: Decimal | None
    purchase_price: Decimal | None
    approval_number: str | None
    purchase_date: date | None
    source_file: str | None
    imported_at: datetime

    model_config = {"from_attributes": True}


class DataUploadResult(BaseModel):
    """엑셀 업로드 결과 — 종합관리시트 + 명품재고대장 합산."""

    file_name: str
    # company_label: 이번 업로드가 어떤 회사로 적재됐는지 (T9 Phase F-A).
    # 명시 안 됐을 때 자동 추출/fallback 으로 결정된 최종 값.
    company_label: str | None = None
    summary_inserted: int = 0
    summary_updated: int = 0
    products_inserted: int = 0
    products_wiped: int = 0
    warnings: list[str] = Field(default_factory=list)


class SendLogOut(BaseModel):
    id: uuid.UUID
    message_id: uuid.UUID
    persona_id: uuid.UUID
    attempt: int
    success: bool | None
    error_code: str | None
    error_detail: str | None
    attempted_at: datetime

    model_config = {"from_attributes": True}
