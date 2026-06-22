"""NAS 자료 검색 모듈 스키마 (Pydantic v2)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class NasStatus(BaseModel):
    """NAS 마운트 + 인덱스 상태 요약."""

    mount_ok: bool
    mount_path: str
    total_files: int
    indexed_files: int
    last_indexed_at: datetime | None = None


class NasCorpusDeptStat(BaseModel):
    """검색 코퍼스의 부서별 청크 수."""

    dept: str
    count: int


class NasCorpusStats(BaseModel):
    """현행 검색 코퍼스(Qdrant docs_text) 현황.

    구 in-app 인덱서(nas_files 테이블, 폐기)가 아니라 실제 검색이 쓰는 Qdrant를
    직접 조회한 값이다. 적재는 외부 파이프라인(tk101-rag/Qwen3)이 담당한다.
    """

    collection: str
    points_count: int  # 적재된 청크(벡터) 수
    by_dept: list[NasCorpusDeptStat] = []


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
    """인덱싱 트리거 요청. subdir로 NAS 하위 폴더만 부분 인덱싱 가능."""

    full_rescan: bool = Field(
        default=False,
        description="True면 file_hash 무관하게 전체 재인덱싱",
    )
    subdir: str | None = Field(
        default=None,
        description=(
            "NAS_MOUNT_PATH 기준 상대 경로 (예: 'MARKETING/04_업무 메뉴얼'). "
            "지정 시 그 하위만 walk. 비어있으면 전체. "
            "검색/다운로드는 항상 root 기준이라 이전 인덱싱 자료는 그대로 검색됨."
        ),
        max_length=500,
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

    dept: str | None = None  # 부서(신사업/RND/마케팅 등) — 출처 표시용
    score: float
    snippet: str


class NasSearchRequest(BaseModel):
    """텍스트 검색 요청.

    필터 필드(file_kinds, path_prefix, mtime_from, mtime_to)는 모두 optional.
    None이면 해당 필터를 적용하지 않는다(기존 동작 보존).
    """

    query: str = Field(min_length=1, max_length=500)
    limit: int = Field(default=20, ge=1, le=50)
    file_kinds: list[Literal["pdf", "word", "ppt", "hwp", "excel"]] | None = Field(
        default=None,
        description=(
            "형식 필터. mime_type IN 매핑으로 변환됨. "
            "hwp는 HWP5(application/x-hwp)와 HWPX(application/vnd.hancom.hwpx) 둘 다 매칭."
        ),
    )
    depts: list[str] | None = Field(
        default=None,
        description=(
            "부서 다중 선택(Qdrant dept payload 라벨, 예: 'RND', '마케팅'). "
            "None/빈 리스트면 전체 부서 검색(권한 스코프 내). 선택 시 그 부서들로 한정하되, "
            "사용자 권한 스코프 밖 부서는 교집합으로 걸러진다."
        ),
    )
    path_prefix: str | None = Field(
        default=None,
        max_length=500,
        description="NAS_MOUNT_PATH 기준 상대 경로 prefix. (예: 'MARKETING/04_업무 메뉴얼')",
    )
    mtime_from: datetime | None = Field(
        default=None,
        description="수정시각 하한(포함). ISO8601.",
    )
    mtime_to: datetime | None = Field(
        default=None,
        description="수정시각 상한(포함). ISO8601.",
    )


class NasSearchResponse(BaseModel):
    results: list[NasSearchHit] = Field(default_factory=list)


class NasDeptStat(BaseModel):
    """검색 코퍼스(Qdrant)의 부서별 청크 수 — 부서 필터 옵션 1건."""

    dept: str
    count: int


class NasDeptsResponse(BaseModel):
    """검색 부서 필터 옵션 응답.

    구 nas_files 기반 폴더 목록(폐기)이 아니라 실제 검색이 쓰는 Qdrant 코퍼스의
    dept facet에서 도출한다 → RND 등 실제 검색 가능한 부서가 모두 노출된다.
    """

    depts: list[NasDeptStat] = Field(default_factory=list)


class NasIndexRunResponse(BaseModel):
    """인덱싱 트리거 응답. 프론트엔드 client 타입과 정합."""

    task_id: str
    status: str
