"""forms 라우터 — 작성 잡 엔드포인트 + 운영 cleanup.

| POST   | /api/forms/jobs                     | 작성 잡 생성                    |
| GET    | /api/forms/jobs/{id}                | 잡 상태 + 매핑 + 출처           |
| POST   | /api/forms/jobs/{id}/sources/upload | 사용자 자료 업로드 (FR-03)      |
| POST   | /api/forms/jobs/{id}/sources/nas    | NAS 자료 추가 (FR-03)           |
| POST   | /api/forms/jobs/{id}/run_mapping    | 매핑 실행 (FR-04, 출처 강제)    |
| PATCH  | /api/forms/jobs/{id}/mappings/{key} | 매핑 수동 수정 (FR-05/FR-08)    |
| POST   | /api/forms/jobs/{id}/regenerate     | 단일 변수 재생성 (Haiku)        |
| POST   | /api/forms/jobs/{id}/render         | .docx 출력 (FR-06)              |
| GET    | /api/forms/jobs/{id}/download       | .docx 다운로드                  |
| GET    | /api/forms/jobs/{id}/revisions      | 변경 이력 (FR-08)               |
| POST   | /api/forms/cleanup                  | 30일 경과 자료 hard delete      |
"""
from __future__ import annotations

import io
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_internal_token
from app.models.user import User
from app.schemas.forms import (
    JobCreateRequest,
    JobDetail,
    JobSummary,
    MappingPatchRequest,
    MappingPayload,
    NasSourceAttachRequest,
    RegenerateRequest,
    RenderRequest,
    RevisionPayload,
)
from app.services.documents import extractor
from app.services.documents.nas_output import save_to_nas
from app.services.form_filler import guardrails, mapper, renderer
from app.services.form_filler.persistence import (
    enforce_status_transition,
    safe_uuid,
    save_upload_file,
    try_load_template_markdown,
)
from app.services.nas_search import bridge as nas_bridge

from ._common import (
    FormDataSource,
    FormJob,
    FormMapping,
    FormRevision,
    FormTemplate,
    _build_job_detail,
    _ensure_models_ready,
    _fetch_job_mappings,
    _fetch_job_or_404,
    _fetch_job_sources,
    _fetch_template_or_404,
    _purge_job_mappings,
    make_router,
)

logger = logging.getLogger(__name__)

router = make_router()


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
# 7-0. GET /api/forms/jobs — 내 작성 잡 목록 (작성 중 문서 resume)
# ---------------------------------------------------------------------------


@router.get("/jobs", response_model=list[JobSummary])
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = 50,
) -> list[JobSummary]:
    """현재 사용자의 작성 잡 목록(최신순). 페이지를 벗어나도 작성 중 문서를 다시
    찾아 이어가도록 라이브러리에서 노출한다."""
    _ensure_models_ready()
    stmt = (
        select(FormJob, FormTemplate.name)
        .outerjoin(FormTemplate, FormJob.template_id == FormTemplate.id)
        .where(FormJob.user_id == user.id)
        .order_by(FormJob.created_at.desc())
        .limit(max(1, min(limit, 200)))
    )
    rows = (await db.execute(stmt)).all()
    return [
        JobSummary(
            id=job.id,
            template_id=job.template_id,
            template_name=tname,
            status=job.status,
            created_at=job.created_at,
            completed_at=job.completed_at,
        )
        for job, tname in rows
    ]


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

    saved_path = save_upload_file(file_bytes, file.filename, str(job_id))

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
    try:
        if body.auto_query:
            # 명시 쿼리: 단일 의미검색.
            hits = await nas_bridge.search_relevant_chunks(
                db, query=body.auto_query, limit=body.limit
            )
            chunk_ids.extend(h.chunk_id for h in hits)
        elif body.auto_query_from_template and job.template_id:
            # 양식 변수 기반: 변수별 병렬 검색으로 자료 커버리지 향상.
            template = await db.get(FormTemplate, job.template_id)
            if template is not None and template.variables:
                hits = await nas_bridge.search_per_variable(
                    db,
                    variables=template.variables,
                    template_name=getattr(template, "name", None),
                )
                chunk_ids.extend(h.chunk_id for h in hits)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc

    file_chunks: list[nas_bridge.NasChunkHit] = []
    if body.nas_file_ids:
        file_chunks += await nas_bridge.fetch_chunks_for_files(
            db, [str(fid) for fid in body.nas_file_ids]
        )
    if body.nas_paths:
        file_chunks += await nas_bridge.fetch_chunks_for_paths(db, body.nas_paths)
    chunk_ids.extend(c.chunk_id for c in file_chunks)

    chunk_ids = list(dict.fromkeys(chunk_ids))  # dedupe, preserve order
    if not chunk_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "추가할 NAS 청크가 없습니다 "
                "(auto_query / auto_query_from_template / nas_paths / nas_file_ids / "
                "nas_chunk_ids 중 1개 이상 필요)"
            ),
        )

    direct = await nas_bridge.fetch_chunks_by_ids(db, chunk_ids)
    chunk_map = {c.chunk_id: c for c in direct + file_chunks}

    inserted: list[dict] = []
    for cid in chunk_ids:
        chunk = chunk_map.get(cid)
        if chunk is None:
            continue
        # 신규 Qdrant 코퍼스는 레거시 nas_files 행이 없다(doc_id 는 UUID도 아님).
        # → nas_file_id=None, 표시·추적용으로 경로는 upload_path, 청크는 point id 보존.
        chunk_uuid = safe_uuid(chunk.chunk_id)
        source = FormDataSource(
            id=uuid.uuid4(),
            job_id=job.id,
            kind="nas_file",
            nas_file_id=None,
            upload_path=chunk.file_path or None,
            nas_chunk_ids=[chunk_uuid] if chunk_uuid else None,
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

    enforce_status_transition(job.status, "mapping")
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
    template_markdown = try_load_template_markdown(template)

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


def _render_mapping_dict(template, mappings_rows) -> dict[str, str | None]:
    """매핑 행 → {variable_key: value}. 값이 None 이고 변수에 default 가 있으면 폴백.

    render(확정 후 다운로드)와 preview(즉석 미리보기)가 동일 규칙을 쓰도록 공유.
    """
    var_defaults = {
        v["key"]: v.get("default")
        for v in (template.variables or [])
        if v.get("default") not in (None, "")
    }
    out: dict[str, str | None] = {}
    for m in mappings_rows:
        value = m.value
        if value is None and m.variable_key in var_defaults:
            value = str(var_defaults[m.variable_key])
        out[m.variable_key] = value
    return out


@router.get("/jobs/{job_id}/preview")
async def preview_job(
    job_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """현재 매핑 상태를 **즉석 렌더**해 .docx bytes 반환.

    render(확정 후 다운로드)와 달리 검수 게이트·NAS 저장·DB 쓰기가 없다. 프론트가
    이 bytes 를 mammoth 로 HTML 변환해 "채워진 양식"을 다운로드 전에 미리 보여준다.
    """
    _ensure_models_ready()
    job = await _fetch_job_or_404(db, job_id, user)
    template = await _fetch_template_or_404(db, job.template_id)
    mappings_rows = await _fetch_job_mappings(db, job.id)
    mapping_dict = _render_mapping_dict(template, mappings_rows)

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
            save_to_nas=False,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    return StreamingResponse(
        io.BytesIO(rendered.file_bytes),
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": 'inline; filename="preview.docx"'},
    )


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
    enforce_status_transition(job.status, "completed")

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

    mapping_dict = _render_mapping_dict(template, mappings_rows)

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

    # 결과물을 부서별 NAS 폴더(문서작업/{부서}/{날짜})에도 사본 저장.
    # 기존 form_filler_output_root 저장과 별개 — best-effort, 실패해도 렌더 정상.
    try:
        save_to_nas(
            rendered.file_bytes,
            department=job.department or user.department,
            filename=rendered.filename,
        )
    except Exception:  # noqa: BLE001 - NAS 저장은 비치명적
        logger.warning("forms render NAS 사본 저장 실패(무시)", exc_info=True)

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
    # separator 없는 startswith 우회(/root-evil ⊂ /root) 차단 — 경계 검사.
    if not (real_target == real_root or real_target.startswith(real_root + os.sep)):
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
