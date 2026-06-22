"""forms 라우터 — 양식(템플릿) 엔드포인트 (FR-01, FR-02, FR-07).

| POST   | /api/forms/templates/analyze  | 양식 업로드 + 자동 분석 (FR-01) |
| GET    | /api/forms/templates          | 라이브러리 목록 (FR-07)         |
| GET    | /api/forms/templates/{id}     | 양식 + 변수                     |
| PATCH  | /api/forms/templates/{id}     | 변수 라벨 수정 (FR-02)          |
| DELETE | /api/forms/templates/{id}     | soft delete                     |
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.forms import (
    TemplateAnalyzeResponse,
    TemplateBrief,
    TemplateDetail,
    TemplateUpdateRequest,
    VariableSchema,
)
from app.services.form_filler import analyzer
from app.services.form_filler.persistence import (
    next_template_version,
    save_template_file,
)

from ._common import (
    FormTemplate,
    _ensure_models_ready,
    _fetch_template_or_404,
    make_router,
)

router = make_router()


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
    saved_path = save_template_file(file_bytes, file_hash, file.filename)
    tags_list = (
        [t.strip() for t in (department_tags or "").split(",") if t.strip()]
        or [user.department]
    )

    # 동일 양식명 다른 file_hash → version 증가.
    version = await next_template_version(db, template_name, FormTemplate)

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
