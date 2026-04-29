"""NAS 파일 인덱스 + 텍스트 청크 모델.

v0.6.0 PoC: 텍스트 임베딩만 지원. 이미지 임베딩/OCR은 다음 버전.
"""
from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base, TimestampMixin, UUIDMixin


class NasFile(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "nas_files"

    # NAS 마운트 기준 절대 경로(또는 정규화된 경로). UNIQUE.
    path = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=True)
    mime_type = Column(Text, nullable=True)
    # 'document' | 'image' (PoC 단계에서는 'document'만 사용)
    file_type = Column(Text, nullable=False, default="document")
    size_bytes = Column(BigInteger, nullable=True)
    mtime = Column(DateTime(timezone=True), nullable=True)
    # 변경 감지용 해시. 처음 1MB SHA1 근사.
    file_hash = Column(Text, nullable=True)
    # 마지막 임베딩 인덱싱 시각. NULL이면 미인덱싱.
    indexed_at = Column(DateTime(timezone=True), nullable=True)
    # 인덱싱 실패 사유. 정상 처리되면 NULL로 리셋.
    last_error = Column(Text, nullable=True)


class NasTextChunk(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "nas_text_chunks"

    file_id = Column(
        UUID(as_uuid=True),
        ForeignKey("nas_files.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    embedding = Column(Vector(1024), nullable=False)
    token_count = Column(Integer, nullable=True)
