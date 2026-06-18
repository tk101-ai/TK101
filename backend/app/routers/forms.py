"""T5 트랙: 범용 문서 자동 작성기 라우터 (PRD T5_범용문서자동작성기 7.3, 14개 엔드포인트).

| 메서드 | 경로                                          | 설명 (FR)                       |
|--------|-----------------------------------------------|---------------------------------|
| POST   | /api/forms/templates/analyze                  | 양식 업로드 + 자동 분석 (FR-01) |
| GET    | /api/forms/templates                          | 라이브러리 목록 (FR-07)         |
| GET    | /api/forms/templates/{id}                     | 양식 + 변수                     |
| PATCH  | /api/forms/templates/{id}                     | 변수 라벨 수정 (FR-02)          |
| DELETE | /api/forms/templates/{id}                     | soft delete                     |
| POST   | /api/forms/jobs                               | 작성 잡 생성                    |
| GET    | /api/forms/jobs/{id}                          | 잡 상태 + 매핑 + 출처           |
| POST   | /api/forms/jobs/{id}/sources/upload           | 사용자 자료 업로드 (FR-03)      |
| POST   | /api/forms/jobs/{id}/sources/nas              | NAS 자료 추가 (FR-03)           |
| POST   | /api/forms/jobs/{id}/run_mapping              | 매핑 실행 (FR-04, 출처 강제)    |
| PATCH  | /api/forms/jobs/{id}/mappings/{key}           | 매핑 수동 수정 (FR-05/FR-08)    |
| POST   | /api/forms/jobs/{id}/regenerate               | 단일 변수 재생성 (Haiku)        |
| POST   | /api/forms/jobs/{id}/render                   | .docx 출력 (FR-06)              |
| GET    | /api/forms/jobs/{id}/download                 | .docx 다운로드                  |
| GET    | /api/forms/jobs/{id}/revisions                | 변경 이력 (FR-08)               |

추가 운영 엔드포인트:
| POST   | /api/forms/cleanup                            | 30일 경과 자료 hard delete (n8n cron) |

NFR-04 환각 방어 5개 방어선 적용 위치:
- #1 DB CHECK form_mappings.value/source_id: alembic 007 (T5-A)
- #2 confidence 임계: services.form_filler.guardrails.filter_low_confidence
- #3 토큰 grounding: services.form_filler.guardrails.verify_token_grounding
- #4 검수 강제 status flow: 본 파일 _enforce_status_transition
- #5 출처 메타 5종: services.form_filler.mapper.MappingResult 강제

T5-A 의존:
- app.models.form_filler: FormTemplate, FormJob, FormDataSource, FormMapping, FormRevision
- app.schemas.form_filler: 위 5개 모델의 Pydantic 응답 스키마

본 라우터는 T5-A 머지 전 시점에서도 임포트 시그니처가 정합하도록 작성됨.
실제 모델/스키마 클래스명이 다를 경우 import 라인만 조정.
"""
from __future__ import annotations

import io
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_internal_token, require_module
from app.models.user import User
from app.modules.constants import Module
from app.services.form_filler import analyzer, extractor, guardrails, mapper, nas_bridge, renderer

logger = logging.getLogger(__name__)


# T5-A의 모델/스키마는 머지 후 별도 PR로 import 라인 통일.
# 본 라우터는 T5-A 모델 클래스가 아래 이름으로 노출된다고 가정한다.
# import 시점 ImportError 방지를 위해 try/except로 감싼다 — T5-A 머지 전이라도 다른 라우터는 정상 부팅.
try:
    from app.models.form_filler import (  # type: ignore[attr-defined]
        FormDataSource,
        FormJob,
        FormMapping,
        FormRevision,
        FormTemplate,
    )
    _T5A_MODELS_READY = True
except ImportError:  # pragma: no cover - T5-A 머지 전 임시 가드
    FormDataSource = FormJob = FormMapping = FormRevision = FormTemplate = None  # type: ignore[assignment]
    _T5A_MODELS_READY = False
    logger.warning(
        "T5-A 모델(form_filler) 미로드 — 라우터는 import만 되고 실행 시 503 반환"
    )


router = APIRouter(
    prefix="/api/forms",
    tags=["forms"],
    dependencies=[Depends(require_module(Module.FORM_FILLER.value))],
)


# ---------------------------------------------------------------------------
# 응답 스키마 (T5-A 의 schemas.form_filler 가 머지될 때까지 본 모듈 안에서 임시 정의)
# ---------------------------------------------------------------------------


class VariableSchema(BaseModel):
    key: str
    label: str
    type: str = "text"
    location: str = ""
    confidence: float = 0.5
    required: bool = False
    default: str | None = None


class TemplateAnalyzeResponse(BaseModel):
    template_id: uuid.UUID
    file_hash: str
    name: str
    version: int
    variables: list[VariableSchema]
    cache_hit: bool = False
    cost_usd: float = 0.0


class TemplateBrief(BaseModel):
    id: uuid.UUID
    name: str
    version: int
    file_hash: str
    department_tags: list[str] = Field(default_factory=list)
    usage_count: int = 0
    created_at: datetime


class TemplateDetail(TemplateBrief):
    variables: list[VariableSchema]
    file_path: str
    file_format: str = "docx"


class TemplateUpdateRequest(BaseModel):
    name: str | None = None
    department_tags: list[str] | None = None
    variables: list[VariableSchema] | None = None


class JobCreateRequest(BaseModel):
    template_id: uuid.UUID
    department: str | None = None


class MappingPayload(BaseModel):
    variable_key: str
    value: str | None
    source_id: uuid.UUID | None
    source_excerpt: str | None
    llm_confidence: float = 0.0
    reasoning: str = ""
    confirmed: bool = False
    manual_override: bool = False


class SourceBrief(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    kind: str
    nas_file_id: uuid.UUID | None = None
    upload_path: str | None = None
    nas_chunk_ids: list[uuid.UUID] = Field(default_factory=list)
    extracted_text: str | None = None
    display_name: str | None = None
    created_at: datetime


class JobDetail(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID | None
    template: TemplateDetail | None = None  # frontend nested 접근 (detail.template.name 등)
    sources: list[SourceBrief] = Field(default_factory=list)
    status: str
    department: str | None
    cost_usd: float = 0.0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    langfuse_trace_id: str | None = None
    error_message: str | None = None
    output_path: str | None = None
    mappings: list[MappingPayload] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime | None = None


class NasSourceAttachRequest(BaseModel):
    nas_file_ids: list[uuid.UUID] = Field(default_factory=list)
    nas_chunk_ids: list[uuid.UUID] = Field(default_factory=list)
    auto_query: str | None = Field(
        default=None,
        description="제공 시 의미 검색으로 chunk_ids 자동 채움. limit는 limit 인자 사용.",
    )
    auto_query_from_template: bool = Field(
        default=False,
        description="True면 auto_query 미지정 시 양식 변수 라벨로 쿼리를 자동 생성해 검색(B2).",
    )
    limit: int = Field(default=20, ge=1, le=50)


class MappingPatchRequest(BaseModel):
    value: str | None = None
    source_id: uuid.UUID | None = None
    source_excerpt: str | None = None
    confirmed: bool | None = None
    feedback_comment: str | None = None


class RegenerateRequest(BaseModel):
    variable_key: str
    user_feedback: str | None = None


class RenderRequest(BaseModel):
    save_to_nas: bool = True


class RevisionPayload(BaseModel):
    id: uuid.UUID
    variable_key: str
    previous_value: str | None
    new_value: str | None
    change_type: str
    feedback_comment: str | None
    changed_at: datetime


class JobStatusUpdate(BaseModel):
    status: str


# ---------------------------------------------------------------------------
# 공통 가드 (T5-A 미머지 시 503)
# ---------------------------------------------------------------------------


def _ensure_models_ready() -> None:
    if not _T5A_MODELS_READY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "T5-A 모델 마이그레이션 미적용 — "
                "alembic upgrade head 후 backend 재기동 필요"
            ),
        )


# ---------------------------------------------------------------------------
# 상태 전이 가드 (NFR-04 #4 검수 강제)
# ---------------------------------------------------------------------------

# 허용 상태 전이 그래프. completed 는 반드시 reviewing 단계를 거쳐야 함.
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "analyzing": {"collecting", "failed"},
    "collecting": {"mapping", "failed"},
    "mapping": {"reviewing", "failed"},
    "reviewing": {"reviewing", "completed", "failed"},  # 검수 단계 내 PATCH 허용
    "completed": set(),  # terminal
    "failed": set(),
}


def _enforce_status_transition(current: str, new: str) -> None:
    """검수 강제 (NFR-04 #4): reviewing 거치지 않은 completed 차단."""
    if current == new:
        return
    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if new not in allowed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"잡 상태 전이 거부: {current} → {new}. "
                f"검수 강제 정책 — completed 는 반드시 reviewing 을 거쳐야 합니다."
            ),
        )


# ---------------------------------------------------------------------------
# 1. POST /api/forms/templates/analyze — 양식 업로드 + 자동 분석 (FR-01)
# ---------------------------------------------------------------------------


@router.post(
    "/templates/analyze",
    response_model=TemplateAnalyzeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_template(
    file: UploadFile = File(...),
    name: str | None = Form(default=None),
    department_tags: str | None = Form(default=None, description="콤마 구분 부서 태그"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TemplateAnalyzeResponse:
    _ensure_models_ready()

    if not file.filename or not file.filename.lower().endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="현재 .docx 양식만 지원합니다 (Phase 0)",
        )

    file_bytes = await file.read()
    max_bytes = settings.form_filler_max_form_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"양식 파일이 {settings.form_filler_max_form_mb}MB 한도를 초과",
        )

    file_hash = analyzer.compute_file_hash(file_bytes)

    # 캐시 hit: 동일 file_hash → 분석 스킵 (FR-01 / FR-07).
    existing = await db.execute(
        select(FormTemplate).where(FormTemplate.file_hash == file_hash)
    )
    existing_row = existing.scalar_one_or_none()
    if existing_row is not None and not getattr(existing_row, "is_deleted", False):
        return TemplateAnalyzeResponse(
            template_id=existing_row.id,
            file_hash=file_hash,
            name=existing_row.name,
            version=int(existing_row.version or 1),
            variables=[VariableSchema(**v) for v in (existing_row.variables or [])],
            cache_hit=True,
            cost_usd=0.0,
        )

    # 캐시 miss → Claude 호출.
    try:
        result = analyzer.analyze_form(
            file_bytes,
            job_metadata={"user_id": str(user.id), "department": user.department},
        )
    except RuntimeError as exc:  # API key 미설정 등 환경 오류
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:  # 파싱/포맷 오류
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    template_name = (
        name.strip() if name and name.strip() else (Path(file.filename).stem or "양식")
    )
    saved_path = _save_template_file(file_bytes, file_hash, file.filename)
    tags_list = (
        [t.strip() for t in (department_tags or "").split(",") if t.strip()]
        or [user.department]
    )

    # 동일 양식명 다른 file_hash → version 증가.
    version = await _next_template_version(db, template_name)

    template_row = FormTemplate(
        id=uuid.uuid4(),
        name=template_name,
        version=version,
        file_hash=file_hash,
        file_path=saved_path,
        file_format="docx",
        variables=[
            {
                "key": v.key, "label": v.label, "type": v.type,
                "location": v.location, "confidence": v.confidence,
                "required": v.required, "default": v.default,
            }
            for v in result.variables
        ],
        department_tags=tags_list,
        owner_dept=user.department,
        usage_count=0,
        is_active=True,
        is_deleted=False,
        created_by=user.id,
    )
    db.add(template_row)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"양식 등록 충돌: {exc.orig}",
        ) from exc
    await db.refresh(template_row)

    return TemplateAnalyzeResponse(
        template_id=template_row.id,
        file_hash=file_hash,
        name=template_row.name,
        version=int(template_row.version or 1),
        variables=[VariableSchema(**v) for v in template_row.variables],
        cache_hit=False,
        cost_usd=result.llm_response.cost_usd,
    )


def _save_template_file(file_bytes: bytes, file_hash: str, original_name: str) -> str:
    """양식 원본을 NAS 출력 루트의 templates 하위에 file_hash 키로 저장."""
    root = Path(settings.form_filler_output_root) / "templates"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{file_hash}{Path(original_name).suffix.lower()}"
    target.write_bytes(file_bytes)
    return str(target)


async def _next_template_version(db: AsyncSession, name: str) -> int:
    stmt = select(FormTemplate).where(FormTemplate.name == name)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return (max((int(r.version or 1) for r in rows), default=0) + 1) if rows else 1


# ---------------------------------------------------------------------------
# 2. GET /api/forms/templates — 라이브러리 목록 (FR-07)
# ---------------------------------------------------------------------------


@router.get("/templates", response_model=list[TemplateBrief])
async def list_templates(
    q: str | None = Query(default=None, description="양식명 부분 일치"),
    department: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[TemplateBrief]:
    _ensure_models_ready()
    stmt = select(FormTemplate).where(FormTemplate.is_deleted.is_(False))
    if q:
        stmt = stmt.where(FormTemplate.name.ilike(f"%{q}%"))
    if department:
        stmt = stmt.where(FormTemplate.department_tags.any(department))
    stmt = stmt.order_by(FormTemplate.usage_count.desc(), FormTemplate.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        TemplateBrief(
            id=r.id, name=r.name, version=int(r.version or 1),
            file_hash=r.file_hash, department_tags=list(r.department_tags or []),
            usage_count=int(r.usage_count or 0), created_at=r.created_at,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 3. GET /api/forms/templates/{id} — 양식 + 변수
# ---------------------------------------------------------------------------


@router.get("/templates/{template_id}", response_model=TemplateDetail)
async def get_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> TemplateDetail:
    _ensure_models_ready()
    row = await _fetch_template_or_404(db, template_id)
    return TemplateDetail(
        id=row.id, name=row.name, version=int(row.version or 1),
        file_hash=row.file_hash, department_tags=list(row.department_tags or []),
        usage_count=int(row.usage_count or 0), created_at=row.created_at,
        variables=[VariableSchema(**v) for v in (row.variables or [])],
        file_path=row.file_path, file_format=row.file_format or "docx",
    )


# ---------------------------------------------------------------------------
# 4. PATCH /api/forms/templates/{id} — 변수 라벨 수정 (FR-02)
# ---------------------------------------------------------------------------


@router.patch("/templates/{template_id}", response_model=TemplateDetail)
async def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdateRequest,
    db: AsyncSession = Depends(get_db),
) -> TemplateDetail:
    _ensure_models_ready()
    row = await _fetch_template_or_404(db, template_id)
    if body.name is not None:
        row.name = body.name
    if body.department_tags is not None:
        row.department_tags = body.department_tags
    if body.variables is not None:
        row.variables = [v.model_dump() for v in body.variables]
    await db.commit()
    await db.refresh(row)
    return TemplateDetail(
        id=row.id, name=row.name, version=int(row.version or 1),
        file_hash=row.file_hash, department_tags=list(row.department_tags or []),
        usage_count=int(row.usage_count or 0), created_at=row.created_at,
        variables=[VariableSchema(**v) for v in (row.variables or [])],
        file_path=row.file_path, file_format=row.file_format or "docx",
    )


# ---------------------------------------------------------------------------
# 5. DELETE /api/forms/templates/{id} — soft delete
# ---------------------------------------------------------------------------


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> None:
    _ensure_models_ready()
    row = await _fetch_template_or_404(db, template_id)
    row.is_deleted = True
    row.is_active = False
    await db.commit()


# ---------------------------------------------------------------------------
# 6. POST /api/forms/jobs — 작성 잡 생성
# ---------------------------------------------------------------------------


@router.post("/jobs", response_model=JobDetail, status_code=status.HTTP_201_CREATED)
async def create_job(
    body: JobCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobDetail:
    _ensure_models_ready()
    template = await _fetch_template_or_404(db, body.template_id)
    job = FormJob(
        id=uuid.uuid4(),
        template_id=template.id,
        user_id=user.id,
        department=body.department or user.department,
        status="collecting",  # 분석은 이미 끝난 상태(template 보유)에서 잡 생성
        cost_usd=0,
        total_tokens_in=0,
        total_tokens_out=0,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return await _build_job_detail(db, job)


# ---------------------------------------------------------------------------
# 7. GET /api/forms/jobs/{id} — 잡 상태 + 매핑 + 출처
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobDetail:
    _ensure_models_ready()
    job = await _fetch_job_or_404(db, job_id, user)
    return await _build_job_detail(db, job)


# ---------------------------------------------------------------------------
# 8. POST /api/forms/jobs/{id}/sources/upload — 사용자 자료 업로드 (FR-03)
# ---------------------------------------------------------------------------


@router.post(
    "/jobs/{job_id}/sources/upload",
    status_code=status.HTTP_201_CREATED,
)
async def upload_source(
    job_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _ensure_models_ready()
    job = await _fetch_job_or_404(db, job_id, user)

    if not file.filename or not extractor.is_supported(file.filename):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"지원 형식: {sorted(extractor.SUPPORTED_EXTENSIONS)}",
        )

    file_bytes = await file.read()
    max_bytes = settings.nas_index_max_file_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"업로드 파일이 {settings.nas_index_max_file_mb}MB 한도를 초과",
        )

    extracted = extractor.extract_and_chunk(file_bytes, file.filename)
    if not extracted.text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="텍스트 추출 결과가 비어있습니다",
        )

    saved_path = _save_upload_file(file_bytes, file.filename, str(job_id))

    source = FormDataSource(
        id=uuid.uuid4(),
        job_id=job.id,
        kind="user_upload",
        upload_path=saved_path,
        extracted_text=extracted.text,
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return {
        "source_id": str(source.id),
        "kind": "user_upload",
        "filename": file.filename,
        "chunks": len(extracted.chunks),
        "extracted_chars": len(extracted.text),
    }


def _save_upload_file(file_bytes: bytes, original_name: str, job_id: str) -> str:
    root = Path(settings.form_filler_upload_root) / job_id
    root.mkdir(parents=True, exist_ok=True)
    safe_name = original_name.replace("/", "_").replace("\\", "_")
    target = root / f"{uuid.uuid4().hex[:8]}_{safe_name}"
    target.write_bytes(file_bytes)
    real_target = os.path.realpath(target)
    real_root = os.path.realpath(settings.form_filler_upload_root)
    if not real_target.startswith(real_root):
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="업로드 경로가 허용 범위를 벗어남",
        )
    return str(target)


# ---------------------------------------------------------------------------
# 9. POST /api/forms/jobs/{id}/sources/nas — NAS 자료 추가 (FR-03)
# ---------------------------------------------------------------------------


@router.post(
    "/jobs/{job_id}/sources/nas",
    status_code=status.HTTP_201_CREATED,
)
async def attach_nas_sources(
    job_id: uuid.UUID,
    body: NasSourceAttachRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    _ensure_models_ready()
    job = await _fetch_job_or_404(db, job_id, user)

    chunk_ids: list[str] = [str(cid) for cid in body.nas_chunk_ids]
    # 검색 쿼리: 명시 auto_query 우선, 없으면 양식 변수로 자동 생성(B2).
    search_query = body.auto_query
    if not search_query and body.auto_query_from_template and job.template_id:
        template = await db.get(FormTemplate, job.template_id)
        if template is not None:
            search_query = nas_bridge.build_query_from_variables(
                template.variables, getattr(template, "name", None)
            )
    if search_query:
        try:
            hits = await nas_bridge.search_relevant_chunks(
                db, query=search_query, limit=body.limit
            )
        except RuntimeError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            ) from exc
        chunk_ids.extend(h.chunk_id for h in hits)

    file_chunks: list[nas_bridge.NasChunkHit] = []
    if body.nas_file_ids:
        file_chunks = await nas_bridge.fetch_chunks_for_files(
            db, [str(fid) for fid in body.nas_file_ids]
        )
        chunk_ids.extend(c.chunk_id for c in file_chunks)

    chunk_ids = list(dict.fromkeys(chunk_ids))  # dedupe, preserve order
    if not chunk_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="추가할 NAS 청크가 없습니다 (auto_query/nas_file_ids/nas_chunk_ids 중 1개 이상 필요)",
        )

    direct = await nas_bridge.fetch_chunks_by_ids(db, chunk_ids)
    chunk_map = {c.chunk_id: c for c in direct + file_chunks}

    inserted: list[dict] = []
    for cid in chunk_ids:
        chunk = chunk_map.get(cid)
        if chunk is None:
            continue
        source = FormDataSource(
            id=uuid.uuid4(),
            job_id=job.id,
            kind="nas_file",
            nas_file_id=uuid.UUID(chunk.file_id),
            nas_chunk_ids=[uuid.UUID(chunk.chunk_id)],
            extracted_text=chunk.content,
        )
        db.add(source)
        inserted.append(
            {"source_id": str(source.id), "file_path": chunk.file_path, "chunk_index": chunk.chunk_index}
        )
    await db.commit()
    return {"attached": inserted, "total": len(inserted)}


# ---------------------------------------------------------------------------
# 10. POST /api/forms/jobs/{id}/run_mapping — 매핑 실행 (FR-04)
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/run_mapping", response_model=JobDetail)
async def run_mapping(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobDetail:
    _ensure_models_ready()
    job = await _fetch_job_or_404(db, job_id, user)
    template = await _fetch_template_or_404(db, job.template_id)

    _enforce_status_transition(job.status, "mapping")
    job.status = "mapping"
    await db.commit()

    sources_rows = await _fetch_job_sources(db, job.id)
    if not sources_rows:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="자료가 1건도 없어 매핑 불가능 — 자료 업로드 또는 NAS 검색 후 재시도",
        )

    variables = [
        mapper.VariablePayload(
            key=v["key"], label=v.get("label", v["key"]), type=v.get("type", "text")
        )
        for v in (template.variables or [])
    ]
    sources_payload = [
        mapper.SourcePayload(
            source_id=str(row.id),
            kind=row.kind,
            excerpt=(row.extracted_text or "")[:1500],
            file_path=getattr(row, "upload_path", None),
        )
        for row in sources_rows
    ]
    template_markdown = _try_load_template_markdown(template)

    try:
        result = mapper.map_sources_to_variables(
            template_markdown=template_markdown,
            variables=variables,
            sources=sources_payload,
            job_metadata={"job_id": str(job.id), "template_id": str(template.id)},
        )
    except RuntimeError as exc:
        job.status = "failed"
        job.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    except ValueError as exc:
        job.status = "failed"
        job.error_message = str(exc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # 기존 매핑 모두 제거 후 재기록 (run_mapping 은 idempotent 한 재계산).
    await _purge_job_mappings(db, job.id)

    for m in result.accepted + result.rejected:
        db.add(
            FormMapping(
                id=uuid.uuid4(),
                job_id=job.id,
                variable_key=m.variable_key,
                value=m.value,
                source_id=uuid.UUID(m.source_id) if m.source_id and guardrails.is_uuid_like(m.source_id) and m.source_id not in {"user_input", "web_search"} else None,
                source_excerpt=m.source_excerpt,
                llm_confidence=m.llm_confidence,
                reasoning=m.reasoning,
                manual_override=False,
                confirmed=False,
            )
        )

    job.status = "reviewing"
    job.cost_usd = float(job.cost_usd or 0) + result.llm_response.cost_usd
    job.total_tokens_in = int(job.total_tokens_in or 0) + result.llm_response.input_tokens
    job.total_tokens_out = int(job.total_tokens_out or 0) + result.llm_response.output_tokens
    if result.llm_response.trace_id:
        job.langfuse_trace_id = result.llm_response.trace_id
    await db.commit()
    await db.refresh(job)
    return await _build_job_detail(db, job)


def _try_load_template_markdown(template: Any) -> str:
    """template.file_path 의 .docx 를 markdown 으로 변환. 실패 시 빈 문자열."""
    try:
        with open(template.file_path, "rb") as f:
            return analyzer.docx_to_markdown(f.read())
    except (OSError, RuntimeError) as exc:
        logger.warning("템플릿 markdown 로드 실패: %s — 빈 문자열 사용", exc)
        return ""


# ---------------------------------------------------------------------------
# 11. PATCH /api/forms/jobs/{id}/mappings/{key} — 매핑 수동 수정 (FR-08)
# ---------------------------------------------------------------------------


@router.patch("/jobs/{job_id}/mappings/{variable_key}", response_model=MappingPayload)
async def patch_mapping(
    job_id: uuid.UUID,
    variable_key: str,
    body: MappingPatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MappingPayload:
    _ensure_models_ready()
    job = await _fetch_job_or_404(db, job_id, user)
    if job.status not in {"reviewing", "mapping"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"매핑 수정은 reviewing/mapping 상태에서만 가능: 현재 {job.status}",
        )

    stmt = select(FormMapping).where(
        and_(FormMapping.job_id == job.id, FormMapping.variable_key == variable_key)
    )
    result = await db.execute(stmt)
    mapping_row = result.scalar_one_or_none()
    if mapping_row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="매핑 없음")

    previous_value = mapping_row.value
    if body.value is not None:
        mapping_row.value = body.value
        mapping_row.manual_override = True
    if body.source_id is not None:
        mapping_row.source_id = body.source_id
    if body.source_excerpt is not None:
        mapping_row.source_excerpt = body.source_excerpt
    if body.confirmed is not None:
        mapping_row.confirmed = body.confirmed

    # 변경 이력 기록 (FR-08).
    db.add(
        FormRevision(
            id=uuid.uuid4(),
            job_id=job.id,
            variable_key=variable_key,
            previous_value=previous_value,
            new_value=mapping_row.value,
            change_type="manual_edit" if body.value is not None else "lock",
            feedback_comment=body.feedback_comment,
            changed_by=user.id,
        )
    )
    await db.commit()
    await db.refresh(mapping_row)
    return MappingPayload(
        variable_key=mapping_row.variable_key,
        value=mapping_row.value,
        source_id=mapping_row.source_id,
        source_excerpt=mapping_row.source_excerpt,
        llm_confidence=float(mapping_row.llm_confidence or 0),
        reasoning=mapping_row.reasoning or "",
        confirmed=bool(mapping_row.confirmed),
        manual_override=bool(mapping_row.manual_override),
    )


# ---------------------------------------------------------------------------
# 12. POST /api/forms/jobs/{id}/regenerate — 단일 변수 재생성 (Haiku)
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/regenerate", response_model=MappingPayload)
async def regenerate_variable(
    job_id: uuid.UUID,
    body: RegenerateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> MappingPayload:
    _ensure_models_ready()
    job = await _fetch_job_or_404(db, job_id, user)
    template = await _fetch_template_or_404(db, job.template_id)

    target_var = next(
        (v for v in (template.variables or []) if v.get("key") == body.variable_key),
        None,
    )
    if target_var is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"변수 키 '{body.variable_key}' 를 양식에서 찾을 수 없음",
        )

    sources_rows = await _fetch_job_sources(db, job.id)
    sources_payload = [
        mapper.SourcePayload(
            source_id=str(row.id),
            kind=row.kind,
            excerpt=(row.extracted_text or "")[:1500],
            file_path=getattr(row, "upload_path", None),
        )
        for row in sources_rows
    ]

    try:
        result, llm_response = mapper.regenerate_one_variable(
            variable=mapper.VariablePayload(
                key=target_var["key"],
                label=target_var.get("label", target_var["key"]),
                type=target_var.get("type", "text"),
            ),
            user_feedback=body.user_feedback or "",
            sources=sources_payload,
            valid_source_ids={s.source_id for s in sources_payload},
            job_metadata={"job_id": str(job.id), "variable_key": body.variable_key},
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    stmt = select(FormMapping).where(
        and_(FormMapping.job_id == job.id, FormMapping.variable_key == body.variable_key)
    )
    existing = await db.execute(stmt)
    mapping_row = existing.scalar_one_or_none()
    previous_value = mapping_row.value if mapping_row else None

    if mapping_row is None:
        mapping_row = FormMapping(
            id=uuid.uuid4(),
            job_id=job.id,
            variable_key=body.variable_key,
        )
        db.add(mapping_row)

    mapping_row.value = result.value
    mapping_row.source_id = (
        uuid.UUID(result.source_id)
        if result.source_id and guardrails.is_uuid_like(result.source_id)
        and result.source_id not in {"user_input", "web_search"}
        else None
    )
    mapping_row.source_excerpt = result.source_excerpt
    mapping_row.llm_confidence = result.llm_confidence
    mapping_row.reasoning = result.reasoning
    mapping_row.manual_override = False
    mapping_row.confirmed = False

    db.add(
        FormRevision(
            id=uuid.uuid4(),
            job_id=job.id,
            variable_key=body.variable_key,
            previous_value=previous_value,
            new_value=mapping_row.value,
            change_type="regenerate",
            feedback_comment=body.user_feedback,
            changed_by=user.id,
        )
    )
    job.cost_usd = float(job.cost_usd or 0) + llm_response.cost_usd
    job.total_tokens_in = int(job.total_tokens_in or 0) + llm_response.input_tokens
    job.total_tokens_out = int(job.total_tokens_out or 0) + llm_response.output_tokens
    await db.commit()
    await db.refresh(mapping_row)
    return MappingPayload(
        variable_key=mapping_row.variable_key,
        value=mapping_row.value,
        source_id=mapping_row.source_id,
        source_excerpt=mapping_row.source_excerpt,
        llm_confidence=float(mapping_row.llm_confidence or 0),
        reasoning=mapping_row.reasoning or "",
        confirmed=bool(mapping_row.confirmed),
        manual_override=bool(mapping_row.manual_override),
    )


# ---------------------------------------------------------------------------
# 13. POST /api/forms/jobs/{id}/render — .docx 출력 (FR-06)
# ---------------------------------------------------------------------------


@router.post("/jobs/{job_id}/render", response_model=JobDetail)
async def render_job(
    job_id: uuid.UUID,
    body: RenderRequest = RenderRequest(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> JobDetail:
    _ensure_models_ready()
    job = await _fetch_job_or_404(db, job_id, user)
    template = await _fetch_template_or_404(db, job.template_id)

    # 검수 강제 (NFR-04 #4): reviewing → completed 만 허용. 직접 completed 설정 차단.
    _enforce_status_transition(job.status, "completed")

    mappings_rows = await _fetch_job_mappings(db, job.id)
    # 모든 required 변수가 confirmed 인지 검사 — 검수 미완료 차단.
    required_keys = {
        v["key"] for v in (template.variables or []) if v.get("required")
    }
    confirmed_keys = {m.variable_key for m in mappings_rows if m.confirmed}
    missing_required = required_keys - confirmed_keys
    if missing_required:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"필수 변수 검수 미완료 — 검수 후 재시도: {sorted(missing_required)}"
            ),
        )

    mapping_dict: dict[str, str | None] = {
        m.variable_key: m.value for m in mappings_rows
    }

    try:
        with open(template.file_path, "rb") as f:
            template_bytes = f.read()
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"양식 원본 로드 실패: {exc}",
        ) from exc

    try:
        rendered = renderer.render_docx(
            template_bytes=template_bytes,
            mappings=mapping_dict,
            template_name=template.name,
            user_id=str(user.id),
            save_to_nas=body.save_to_nas,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc

    job.output_path = rendered.output_path
    job.status = "completed"
    job.completed_at = datetime.now(tz=timezone.utc)
    template.usage_count = int(template.usage_count or 0) + 1
    await db.commit()
    await db.refresh(job)
    return await _build_job_detail(db, job)


# ---------------------------------------------------------------------------
# 14. GET /api/forms/jobs/{id}/download — .docx 다운로드
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/download")
async def download_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    _ensure_models_ready()
    job = await _fetch_job_or_404(db, job_id, user)
    if job.status != "completed" or not job.output_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="출력 파일이 없습니다 — render 호출 후 다시 시도",
        )
    real_target = os.path.realpath(job.output_path)
    real_root = os.path.realpath(settings.form_filler_output_root)
    if not real_target.startswith(real_root):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="출력 경로 위반"
        )
    if not os.path.isfile(real_target):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="출력 파일이 디스크에 존재하지 않습니다",
        )
    file_bytes = Path(real_target).read_bytes()
    filename = Path(real_target).name
    return StreamingResponse(
        io.BytesIO(file_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# 15. GET /api/forms/jobs/{id}/revisions — 변경 이력 (FR-08)
# ---------------------------------------------------------------------------


@router.get("/jobs/{job_id}/revisions", response_model=list[RevisionPayload])
async def list_revisions(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RevisionPayload]:
    _ensure_models_ready()
    job = await _fetch_job_or_404(db, job_id, user)
    stmt = (
        select(FormRevision)
        .where(FormRevision.job_id == job.id)
        .order_by(FormRevision.changed_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [
        RevisionPayload(
            id=r.id,
            variable_key=r.variable_key,
            previous_value=r.previous_value,
            new_value=r.new_value,
            change_type=r.change_type,
            feedback_comment=r.feedback_comment,
            changed_at=r.changed_at,
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# 16. POST /api/forms/cleanup — 30일 경과 자료 hard delete (n8n cron, T5-D 호출)
# ---------------------------------------------------------------------------


@router.post(
    "/cleanup",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_internal_token)],
)
async def cleanup_expired(db: AsyncSession = Depends(get_db)) -> dict:
    _ensure_models_ready()
    cutoff = datetime.now(tz=timezone.utc) - timedelta(
        days=settings.form_filler_upload_retention_days
    )
    stmt = select(FormDataSource).where(
        and_(
            FormDataSource.kind == "user_upload",
            FormDataSource.created_at < cutoff,
        )
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    deleted_files = 0
    for row in rows:
        if row.upload_path and os.path.isfile(row.upload_path):
            try:
                os.unlink(row.upload_path)
                deleted_files += 1
            except OSError as exc:
                logger.warning("자료 파일 삭제 실패: %s (%s)", row.upload_path, exc)
        await db.delete(row)
    await db.commit()
    return {
        "cutoff": cutoff.isoformat(),
        "deleted_sources": len(rows),
        "deleted_files": deleted_files,
    }


# ---------------------------------------------------------------------------
# 보조 함수
# ---------------------------------------------------------------------------


async def _fetch_template_or_404(db: AsyncSession, template_id: uuid.UUID) -> Any:
    stmt = select(FormTemplate).where(FormTemplate.id == template_id)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None or getattr(row, "is_deleted", False):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="양식 없음")
    return row


async def _fetch_job_or_404(db: AsyncSession, job_id: uuid.UUID, user: User) -> Any:
    stmt = select(FormJob).where(FormJob.id == job_id)
    result = await db.execute(stmt)
    job = result.scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="잡 없음")
    # MVP: 본인 잡만 접근. admin 우회는 require_module 단계에서 이미 통과.
    if user.role != "admin" and str(job.user_id) != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="다른 사용자의 잡 접근 거부"
        )
    return job


async def _fetch_job_sources(db: AsyncSession, job_id: uuid.UUID) -> list:
    stmt = select(FormDataSource).where(FormDataSource.job_id == job_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _fetch_job_mappings(db: AsyncSession, job_id: uuid.UUID) -> list:
    stmt = select(FormMapping).where(FormMapping.job_id == job_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def _purge_job_mappings(db: AsyncSession, job_id: uuid.UUID) -> None:
    stmt = select(FormMapping).where(FormMapping.job_id == job_id)
    result = await db.execute(stmt)
    for row in result.scalars().all():
        await db.delete(row)
    await db.flush()


async def _build_job_detail(db: AsyncSession, job: Any) -> JobDetail:
    mappings = await _fetch_job_mappings(db, job.id)

    # template 채움 — frontend가 detail.template.name, .variables 등을 직접 접근.
    template_detail = None
    if job.template_id:
        tpl_row = await db.get(FormTemplate, job.template_id)
        if tpl_row is not None:
            template_detail = TemplateDetail(
                id=tpl_row.id,
                name=tpl_row.name,
                version=int(tpl_row.version or 1),
                file_hash=tpl_row.file_hash,
                department_tags=list(tpl_row.department_tags or []),
                usage_count=int(tpl_row.usage_count or 0),
                created_at=tpl_row.created_at,
                variables=[VariableSchema(**v) for v in (tpl_row.variables or [])],
                file_path=tpl_row.file_path,
                file_format=tpl_row.file_format or "docx",
            )

    # sources 채움 — frontend가 detail.sources.length 등 직접 접근.
    src_stmt = select(FormDataSource).where(FormDataSource.job_id == job.id)
    src_result = await db.execute(src_stmt)
    src_rows = src_result.scalars().all()
    sources_list = [
        SourceBrief(
            id=s.id,
            job_id=s.job_id,
            kind=s.kind,
            nas_file_id=s.nas_file_id,
            upload_path=s.upload_path,
            nas_chunk_ids=list(s.nas_chunk_ids or []),
            extracted_text=s.extracted_text,
            display_name=None,
            created_at=s.created_at,
        )
        for s in src_rows
    ]

    return JobDetail(
        id=job.id,
        template_id=job.template_id,
        template=template_detail,
        sources=sources_list,
        status=job.status,
        department=job.department,
        cost_usd=float(job.cost_usd or 0),
        total_tokens_in=int(job.total_tokens_in or 0),
        total_tokens_out=int(job.total_tokens_out or 0),
        langfuse_trace_id=job.langfuse_trace_id,
        error_message=job.error_message,
        output_path=job.output_path,
        mappings=[
            MappingPayload(
                variable_key=m.variable_key,
                value=m.value,
                source_id=m.source_id,
                source_excerpt=m.source_excerpt,
                llm_confidence=float(m.llm_confidence or 0),
                reasoning=m.reasoning or "",
                confirmed=bool(m.confirmed),
                manual_override=bool(m.manual_override),
            )
            for m in mappings
        ],
        created_at=job.created_at,
        completed_at=job.completed_at,
    )
