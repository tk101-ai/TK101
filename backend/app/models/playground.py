"""AI Playground 모델 — 세션/메시지/미디어 (T8 PRD).

세션-메시지 분리:
- 세션은 메타 (provider/model/system_prompt/temperature) 만 보관.
- 메시지는 role(user/assistant) + content + 토큰/지연/모델 메트릭.
- raw_request/raw_response 는 JSONB. Authorization 헤더는 라우터에서 ***masked*** 치환.

기존 모델 패턴 (account.py/transaction.py) 을 따라 ``Column(...)`` 스타일 사용.
SQLAlchemy 2.0 typed style (Mapped) 은 review_translation.py 와 base.py 가 혼용 중이라
일관성 유지를 위해 column 기반으로 통일.
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin, UUIDMixin


class PlaygroundSession(UUIDMixin, TimestampMixin, Base):
    """LLM 채팅 세션 1개. provider/model 은 세션 단위로 고정."""

    __tablename__ = "playground_sessions"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    title = Column(String(200), nullable=True)
    # provider: "claude" | "openai" | "gemini" 등. Phase 1은 claude만.
    provider = Column(String(50), nullable=False)
    # model: 정확한 모델 ID. 변형 chip 선택 시 이 컬럼 값이 변경됨.
    model = Column(String(100), nullable=False)
    system_prompt = Column(Text, nullable=True)
    # 0.00 ~ 2.00 범위. 기본 0.70 (Anthropic default).
    temperature = Column(
        Numeric(3, 2), nullable=False, server_default=text("0.70")
    )


class PlaygroundMessage(UUIDMixin, Base):
    """세션 내 메시지 1개 + LLM 호출 메트릭.

    timestamp:
    - created_at 만 보관. 메시지는 immutable (수정 불가) 라서 updated_at 불필요.
    """

    __tablename__ = "playground_messages"

    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("playground_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # role: "user" | "assistant" | "system".
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    # 메트릭 — assistant 메시지에만 채워짐.
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    # extended thinking (Opus) 사용 시 분리된 reasoning 토큰.
    reasoning_tokens = Column(Integer, nullable=True)
    # prompt caching read/creation 합계.
    cached_tokens = Column(Integer, nullable=True)
    total_tokens = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    model = Column(String(100), nullable=True)
    # 단가표 적용 후 산출된 비용 (USD). 모델별 input/cache/output 단가 × 토큰.
    cost_usd = Column(Numeric(12, 6), nullable=True)
    # raw_request: 마스킹된 요청 payload. raw_response: final usage chunk.
    raw_request = Column(JSONB, nullable=True)
    raw_response = Column(JSONB, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlaygroundAttachment(UUIDMixin, Base):
    """LLM 채팅 입력에 첨부할 파일 (이미지/PDF/텍스트).

    /chat 호출 시 ``attachment_ids`` 로 참조됨. PDF/텍스트는 업로드 시점에
    텍스트 추출해 ``extracted_text`` 에 저장 → /chat 이 사용자 메시지 본문
    앞에 inline 으로 prepend. 이미지는 vision-capable 모델일 때만 data URL
    로 동봉.
    """

    __tablename__ = "playground_attachments"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # 업로드 시점에 세션이 있으면 그 세션 id, 새 세션이면 null → /chat 시 세션과 연결.
    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("playground_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )
    # kind: "image" | "pdf" | "text".
    kind = Column(String(20), nullable=False)
    filename = Column(String(300), nullable=False)
    mime = Column(String(150), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    file_path = Column(String(700), nullable=False)
    # PDF/텍스트의 추출 본문. 너무 길면 라우터에서 truncate.
    extracted_text = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PlaygroundMedia(UUIDMixin, Base):
    """Phase 4~5 미디어 생성 결과 (이미지/영상/오디오).

    2026-05-19 영속화 보강:
    - 텐센트 task 1개당 1 row. 생성 시점에 status=pending 으로 미리 만듦.
    - 폴링 결과 받으면 status/url/file_path/error_message 업데이트.
    - 텐센트 임시 URL은 7일 만료 (expires_at) → 즉시 백엔드 디스크로 다운로드.
    """

    __tablename__ = "playground_media"

    session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("playground_sessions.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # media_type: "image" | "video" | "audio".
    media_type = Column(String(20), nullable=False)
    # i2v 등에서 참고한 소스 이미지 row(같은 테이블). 영상이 어떤 이미지로
    # 만들어졌는지 표시용. 소스 삭제 시 SET NULL.
    source_media_id = Column(
        UUID(as_uuid=True),
        ForeignKey("playground_media.id", ondelete="SET NULL"),
        nullable=True,
    )
    # 텐센트 task_id — 폴링 키. unique.
    task_id = Column(String(200), nullable=True, unique=True)
    # "Kling:2.1" 같은 ModelName:Version 합성. 단가 매칭에 사용.
    model_key = Column(String(100), nullable=True)
    prompt = Column(Text, nullable=True)
    # 상태: pending → running → succeeded | failed.
    status = Column(String(20), nullable=False, server_default="pending")
    error_message = Column(Text, nullable=True)
    # 텐센트 임시 URL (7일 만료).
    url = Column(String, nullable=True)
    # 백엔드 디스크에 다운로드한 파일의 절대 경로 — 영구 보관.
    file_path = Column(String(500), nullable=True)
    # 영상/오디오 길이 (초).
    duration_sec = Column(Numeric(8, 2), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    cost_usd = Column(Numeric(10, 6), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    # 콘텐츠 라이브러리 공유: True 면 playground 모듈 사용자 전체에게 공유 갤러리로 노출.
    # 소유자만 토글 가능. shared_at 은 공유로 켠 시각(공유 갤러리 정렬용).
    is_shared = Column(
        Boolean, nullable=False, server_default=text("false")
    )
    shared_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
