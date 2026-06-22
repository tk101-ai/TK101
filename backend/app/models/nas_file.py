"""NAS 파일 인덱스 모델.

검색 코퍼스는 Qdrant(Qwen3) 단일 소스다. 과거 레거시 pgvector 청크 테이블
(nas_text_chunks, e5 1024-dim)은 검색 미반영 dead data여서 제거됨(032 마이그레이션).
이 모델은 NAS 파일 메타(목록/다운로드/상태)만 담는다.
"""
from sqlalchemy import BigInteger, Column, DateTime, Text

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
