"""문서 생성(docgen) 영속화 모델 — 사용자별 생성 문서 저장/재열람 (#1).

docgen 의 /generate 는 무상태였다. 생성 결과를 사용자별로 저장해 나중에
다시 열어 재렌더/다운로드/출처 확인할 수 있도록 한다. AI Playground 세션
패턴(per-user, UUIDMixin/TimestampMixin, user_id FK CASCADE)을 따른다.

기존 모델 패턴(playground.py)을 따라 ``Column(...)`` 스타일 사용.
"""
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base, TimestampMixin, UUIDMixin


class DocgenDocument(UUIDMixin, TimestampMixin, Base):
    """생성된 문서 1건. 섹션/출처는 JSONB 로 통째 보관해 재열람 시 그대로 복원."""

    __tablename__ = "docgen_documents"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 생성 시점 사용자 부서(스냅샷). 사용자 부서가 바뀌어도 생성 당시 값 유지.
    department = Column(String(100), nullable=True)
    title = Column(String(300), nullable=False)
    # 작성 요구/주제(생성 입력). 검색(ILIKE) 대상.
    topic = Column(String, nullable=True)
    # doc_type: "제안서" | "계획서" | "보고서" | "일반".
    doc_type = Column(String(50), nullable=True)
    # source_mode: "rag" | "uploaded" | "both".
    source_mode = Column(String(20), nullable=True)
    # sections: [{heading, body}, ...] — 본문 전체.
    sections = Column(JSONB, nullable=False, server_default="[]")
    # sources: DocSourceRef 목록 [{path, score, name, source_type, doc_id}, ...].
    sources = Column(JSONB, nullable=True)
    # 생성에 쓰인 LLM 모델 ID.
    model = Column(String(100), nullable=True)
    # created_at/updated_at 은 TimestampMixin 에서 제공.


class DocgenRetouchPrompt(UUIDMixin, TimestampMixin, Base):
    """리터치 프롬프트(=디자인/내용 프리셋) 1건.

    생성된 문서를 다른 AI로 재디자인/재생성할 때 쓰는 고품질 크리에이티브
    브리프를 저장한다. 개인 보관함 기본, ``is_shared`` 토글로 전사 공유
    (playground_media 공유 패턴과 동일). 원본 문서가 삭제돼도 프리셋은
    독립적으로 유지(SET NULL).
    """

    __tablename__ = "docgen_retouch_prompts"

    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # 생성 시점 사용자 부서(스냅샷).
    department = Column(String(100), nullable=True)
    # 이 프롬프트를 만들어낸 원본 문서(있으면). 문서 삭제 시 NULL 로 끊김.
    source_document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("docgen_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    title = Column(String(300), nullable=False)
    # doc_type: "제안서" | "계획서" | "보고서" | "일반" (필터/매칭용).
    doc_type = Column(String(50), nullable=True)
    # target: 어떤 AI용으로 다듬었는지. general/gamma/gpt/gemini/internal.
    target = Column(String(20), nullable=False, server_default="general")
    # 프롬프트 본문(사람이 읽는 브리프). 외부 핸드오프/내부 재생성 양쪽에서 사용.
    prompt_text = Column(Text, nullable=False)
    # 공유 토글: True 면 form_filler 모듈 사용자 전체에게 공유 프리셋으로 노출.
    is_shared = Column(Boolean, nullable=False, server_default=text("false"))
    shared_at = Column(DateTime(timezone=True), nullable=True)
    # created_at/updated_at 은 TimestampMixin 에서 제공.
