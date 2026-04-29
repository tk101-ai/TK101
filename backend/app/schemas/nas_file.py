"""NAS 자료 검색 모듈 스키마 (Pydantic v2)."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class NasStatus(BaseModel):
    """NAS 마운트 + 인덱스 상태 요약."""

    mount_ok: bool
    mount_path: str
    total_files: int
    indexed_files: int
    last_indexed_at: datetime | None = None


class NasIndexProgress(BaseModel):
    """백그라운드 인덱싱 진행률 스냅샷."""

    running: bool
    processed: int = 0
    total: int = 0
    current_path: str | None = None
    errors: int = 0
    started_at: datetime | None = None
    finished_at: datetime | None = None
    last_error: str | None = None


class NasIndexRunRequest(BaseModel):
    """인덱싱 트리거 요청. 추후 path/depth 등 옵션 확장 여지."""

    full_rescan: bool = Field(
        default=False,
        description="True면 file_hash 무관하게 전체 재인덱싱",
    )


class NasFileInfo(BaseModel):
    """파일 메타. /search 결과 및 다운로드 메타에서 공통 사용.

    DB 컬럼은 `size_bytes`이지만 응답 필드는 `size`로 노출(프론트엔드 API 계약).
    """

    id: uuid.UUID
    path: str
    name: str | None = None
    file_type: str
    mime_type: str | None = None
    size: int | None = None
    mtime: datetime | None = None


class NasSearchHit(NasFileInfo):
    """파일별 가장 유사도 높은 청크 1개를 대표로 묶어 반환."""

    score: float
    snippet: str


class NasSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=50)


class NasSearchResponse(BaseModel):
    results: list[NasSearchHit] = Field(default_factory=list)


class NasIndexRunResponse(BaseModel):
    """인덱싱 트리거 응답. 프론트엔드 client 타입과 정합."""

    task_id: str
    status: str
