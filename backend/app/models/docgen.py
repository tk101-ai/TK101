"""문서 생성(docgen) 영속화 모델 — 사용자별 생성 문서 저장/재열람 (#1).

docgen 의 /generate 는 무상태였다. 생성 결과를 사용자별로 저장해 나중에
다시 열어 재렌더/다운로드/출처 확인할 수 있도록 한다. AI Playground 세션
패턴(per-user, UUIDMixin/TimestampMixin, user_id FK CASCADE)을 따른다.

기존 모델 패턴(playground.py)을 따라 ``Column(...)`` 스타일 사용.
"""
from sqlalchemy import (
    Column,
    ForeignKey,
    String,
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
