"""AI Playground Pydantic 스키마 (T8 PRD Phase 1).

엔드포인트 매핑:
- GET  /api/playground/providers          → list[PlaygroundProviderMeta]
- POST /api/playground/sessions           → PlaygroundSessionOut
- GET  /api/playground/sessions           → list[PlaygroundSessionOut]
- GET  /api/playground/sessions/{id}/...  → list[PlaygroundMessageOut]
- POST /api/playground/chat (SSE)         → text/event-stream
"""
from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Provider / Model 메타 — UI 변형 chip 노출용
# ---------------------------------------------------------------------------


class PlaygroundModelChip(BaseModel):
    """단일 모델 변형 chip.

    key:   API 호출 시 사용할 정확한 모델 ID (예: claude-opus-4-7).
    label: UI 표시명 (예: "Opus 4.7").
    badge: 옵션 배지 텍스트 (예: "1M", "최신"). 없으면 None.
    """

    key: str
    label: str
    badge: str | None = None


class PlaygroundProviderMeta(BaseModel):
    """Provider 카드 1개 + 그 안의 변형 chip 목록."""

    provider_key: str
    provider_label: str
    models: list[PlaygroundModelChip]


# ---------------------------------------------------------------------------
# 채팅 요청 / 세션 / 메시지
# ---------------------------------------------------------------------------


class PlaygroundChatRequest(BaseModel):
    """POST /api/playground/chat 요청 본문 (SSE 스트리밍)."""

    # session_id 가 None 이면 라우터가 새 세션을 생성.
    session_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=200_000, description="사용자 메시지")
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    # Anthropic Messages API 허용 범위 (0.0 ~ 1.0). UI 에서 더 넓힐 일 없음.
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)
    # 2026-05-20: 채팅 입력에 첨부할 파일 ID 목록. 업로드는 별도 endpoint.
    attachment_ids: list[uuid.UUID] = Field(default_factory=list)
    # 2026-06-18: NAS RAG. True 면 답변 전에 회사 NAS 문서(Qdrant 코퍼스)에서 관련
    # 청크를 검색해 system 컨텍스트로 주입한다. 검색 실패/0건은 일반 채팅으로 진행.
    use_nas_rag: bool = False


# ---------------------------------------------------------------------------
# 첨부 파일 (2026-05-20 추가)
# ---------------------------------------------------------------------------


class PlaygroundAttachmentOut(BaseModel):
    """업로드된 첨부 파일 1건."""

    id: uuid.UUID
    user_id: uuid.UUID
    session_id: uuid.UUID | None
    kind: str  # "image" | "pdf" | "text" | "docx"
    filename: str
    mime: str
    size_bytes: int
    has_extracted_text: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class PlaygroundSessionCreate(BaseModel):
    """POST /api/playground/sessions 요청 본문 — 빈 세션 생성용."""

    title: str | None = Field(default=None, max_length=200)
    provider: str = Field(min_length=1, max_length=50)
    model: str = Field(min_length=1, max_length=100)
    system_prompt: str | None = Field(default=None, max_length=20_000)
    temperature: float = Field(default=0.7, ge=0.0, le=1.0)


class PlaygroundSessionOut(BaseModel):
    """세션 조회/생성 응답."""

    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    provider: str
    model: str
    system_prompt: str | None
    temperature: Decimal
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class PlaygroundMessageOut(BaseModel):
    """메시지 조회 응답. 메트릭은 assistant 메시지에서만 채워짐."""

    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    input_tokens: int | None
    output_tokens: int | None
    reasoning_tokens: int | None
    cached_tokens: int | None
    total_tokens: int | None
    latency_ms: int | None
    model: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Image / Video — Phase 4/5 뼈대 (DB 영속화 없이 task_id 회전)
# ---------------------------------------------------------------------------


class PlaygroundMediaModelOption(BaseModel):
    """이미지/영상 모델 선택 chip."""

    key: str  # "GEM:3.1" 같은 Name:Version 합성 키
    label: str
    badge: str | None = None


class PlaygroundImageRequest(BaseModel):
    """POST /api/playground/image 요청 본문."""

    prompt: str = Field(min_length=1, max_length=4000)
    model_key: str = Field(default="GEM:3.1", max_length=100)
    negative_prompt: str | None = Field(default=None, max_length=2000)
    aspect_ratio: str = Field(default="1:1", max_length=20)
    enhance_prompt: bool = True
    # 2026-05-20: 사용자 업로드한 베이스 이미지 (playground_attachments.id).
    # 텐센트 reference-image spec 확인 후 정식 활성화. 현재는 graceful 503.
    reference_attachment_id: uuid.UUID | None = None


class PlaygroundVideoRequest(BaseModel):
    """POST /api/playground/video 요청 본문."""

    prompt: str = Field(min_length=1, max_length=4000)
    model_key: str = Field(default="Kling:3.0-Omni", max_length=100)
    duration: int = Field(default=5, ge=1, le=60)
    resolution: str = Field(default="720P", max_length=20)
    aspect_ratio: str = Field(default="16:9", max_length=20)
    audio_generation: bool = False
    enhance_prompt: bool = True
    # 2026-05-20: 사용자 업로드한 베이스 이미지 (playground_attachments.id).
    # 텐센트 reference-image spec 확인 후 정식 활성화.
    reference_attachment_id: uuid.UUID | None = None


class PlaygroundTaskCreated(BaseModel):
    """이미지/영상 작업 생성 응답."""

    task_id: str
    request_id: str | None = None
    kind: str  # "image" | "video"


class PlaygroundTaskStatus(BaseModel):
    """이미지/영상 작업 폴링 응답."""

    task_id: str
    kind: str  # "image" | "video"
    status: str  # "pending" | "running" | "succeeded" | "failed" | "unknown"
    output_url: str | None = None
    error_message: str | None = None
    raw: dict | None = None
    # 백엔드 DB 의 PlaygroundMedia.id — 다운로드 버튼이 안정 URL (/api/playground/media/{id}/file)
    # 을 사용할 수 있게 폴링 응답에 같이 노출. 2026-05-19 추가.
    media_id: uuid.UUID | None = None


# ---------------------------------------------------------------------------
# 미디어 영속화 — 본인 갤러리 목록
# ---------------------------------------------------------------------------


class PlaygroundMediaOut(BaseModel):
    """playground_media 1행 응답 (갤러리 목록용)."""

    id: uuid.UUID
    media_type: str  # "image" | "video"
    source_media_id: uuid.UUID | None = None  # i2v 참고 이미지 row
    task_id: str | None
    model_key: str | None
    prompt: str | None
    status: str
    error_message: str | None
    # 텐센트 임시 URL (만료 시 None 가능) + 백엔드 자체 서빙 URL (/api/playground/media/{id}/file).
    url: str | None
    file_path: str | None
    duration_sec: Decimal | None
    width: int | None
    height: int | None
    cost_usd: Decimal | None
    expires_at: datetime | None
    # 콘텐츠 라이브러리 공유 여부 (소유자만 토글).
    is_shared: bool = False
    shared_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SharedMediaOut(PlaygroundMediaOut):
    """공유 갤러리 1행 — 본인 미디어 응답 + 소유자 표기.

    ``is_mine`` 은 조회자가 소유자인지(공유 갤러리에 본인 것도 같이 노출되므로).
    소유자 이름/부서는 users 조인으로 채운다(모델 컬럼이 아니라 수동 구성).
    """

    owner_name: str | None = None
    owner_department: str | None = None
    is_mine: bool = False


class MediaShareRequest(BaseModel):
    """PATCH /media/{id}/share 요청 — 공유 on/off 토글."""

    is_shared: bool


# ---------------------------------------------------------------------------
# 사용량 대시보드 (admin only)
# ---------------------------------------------------------------------------


class PlaygroundUsageByModel(BaseModel):
    """모델별 집계 1행."""

    model: str
    kind: str  # "text" | "image" | "video"
    request_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class PlaygroundUsageByUser(BaseModel):
    """사용자별 집계 1행."""

    user_id: uuid.UUID
    user_email: str
    request_count: int
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal


class PlaygroundUsageReport(BaseModel):
    """관리자 대시보드용 통합 응답.

    period: 시작·종료 (ISO 8601). 빈 값이면 전체 기간.
    """

    period_start: datetime | None
    period_end: datetime | None
    total_cost_usd: Decimal
    total_requests: int
    by_model: list[PlaygroundUsageByModel]
    by_user: list[PlaygroundUsageByUser]


# ---------------------------------------------------------------------------
# 2026-05-19 백엔드 확장 — quota / 세션 제목 / 관리자 페이지 / i2v
# ---------------------------------------------------------------------------


class PlaygroundQuotaInfo(BaseModel):
    """GET /api/playground/me/quota 응답 (본인 한도+사용량)."""

    monthly_quota_usd: Decimal
    current_usage_usd: Decimal
    remaining_usd: Decimal
    period_start: datetime
    period_end: datetime


class PlaygroundSessionTitleUpdate(BaseModel):
    """PATCH /api/playground/sessions/{id} 요청 본문."""

    title: str = Field(min_length=1, max_length=200)


class PlaygroundAdminSessionOut(BaseModel):
    """관리자 전 세션 목록 1행 — JOIN users 로 email 포함."""

    id: uuid.UUID
    user_id: uuid.UUID
    user_email: str
    title: str | None
    provider: str
    model: str
    created_at: datetime
    updated_at: datetime | None

    model_config = {"from_attributes": True}


class PlaygroundAdminUserQuotaOut(BaseModel):
    """관리자 사용자별 한도+이번 월 사용량 1행."""

    user_id: uuid.UUID
    user_email: str
    user_name: str
    department: str
    role: str
    monthly_quota_usd: Decimal
    current_usage_usd: Decimal
    remaining_usd: Decimal


class PlaygroundAdminQuotaUpdate(BaseModel):
    """PUT /api/playground/admin/users/{id}/quota 요청 본문."""

    monthly_quota_usd: Decimal = Field(ge=0)


class PlaygroundI2VRequest(BaseModel):
    """POST /api/playground/video/from-media 요청 본문.

    image_media_id 로 본인의 완료된 이미지 task 를 참조해 i2v 영상 생성.
    """

    prompt: str = Field(min_length=1, max_length=4000)
    image_media_id: uuid.UUID
    model_key: str = Field(default="Kling:3.0-Omni", max_length=100)
    duration: int = Field(default=5, ge=1, le=60)
    resolution: str = Field(default="720P", max_length=20)
    aspect_ratio: str = Field(default="16:9", max_length=20)
    audio_generation: bool = False
    enhance_prompt: bool = True


class PlaygroundMediaCleanupOut(BaseModel):
    """POST /api/playground/admin/media/cleanup 응답 (보존기간 정리 결과)."""

    scanned: int
    deleted_rows: int
    deleted_files: int
    file_errors: int
    retention_days: int
    cutoff: datetime
