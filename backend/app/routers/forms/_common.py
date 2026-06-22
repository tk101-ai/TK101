"""forms 라우터 패키지 공통 모듈.

- T5-A 모델(form_filler) import 가드(_T5A_MODELS_READY) + _ensure_models_ready
- 공용 APIRouter 생성 헬퍼(make_router)
- DB 조회/직렬화 보조 함수(_fetch_*, _build_job_detail)

forms.py(단일 1350줄)를 분할(동작 동일 리팩터)한 결과로, 로직/예외/쿼리는 원본과 동일하다.
"""
from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import require_module
from app.models.user import User
from app.modules.constants import Module
from app.schemas.forms import (
    JobDetail,
    MappingPayload,
    SourceBrief,
    TemplateDetail,
    VariableSchema,
)

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


def make_router() -> APIRouter:
    """forms 서브라우터 생성 — prefix/tags/모듈 권한 의존성 동일."""
    return APIRouter(
        prefix="/api/forms",
        tags=["forms"],
        dependencies=[Depends(require_module(Module.FORM_FILLER.value))],
    )


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
