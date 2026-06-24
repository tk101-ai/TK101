"""요구 기반 문서 생성 라우터 (T5 확장).

POST /api/docgen/generate     — 주제+NAS RAG → 구조화 초안(마크다운+섹션+출처) 반환.
POST /api/docgen/render       — (수정된) 초안 → .docx 다운로드.
POST /api/docgen/render_pptx  — (수정된) 초안 → .pptx 다운로드.

권한: 문서작성 모듈(form_filler) 재사용. LLM/검색은 form_filler 빌딩블록 재사용.
"""
from __future__ import annotations

import asyncio
import io
import logging
import urllib.parse
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_module
from app.models.docgen import DocgenDocument
from app.models.form_filler import FormJob
from app.modules.constants import Module, UserRole
from app.models.user import User
from pydantic import TypeAdapter, ValidationError

from app.schemas.docgen import (
    DocGenResponse,
    DocgenDocumentBrief,
    DocgenDocumentDetail,
    DocRenderRequest,
    DocReviewResponse,
    DocSection,
    DocSectionRegenResponse,
    DocSectionReview,
    DocSourceRef,
    DocType,
    SourceMode,
)
from app.config import settings
from app.services.docgen import (
    build_docx,
    build_pptx,
    generate_document,
    generate_document_reviewed,
    regenerate_section,
    render_markdown,
    review_document,
)
from app.services.documents.nas_output import save_to_nas
from app.services.documents.sources import collect_sources

# 업로드 참고자료 가드 — 파일 수/크기 상한.
_MAX_UPLOAD_FILES = 5
_MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 파일당 20MB

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/docgen",
    tags=["docgen"],
    dependencies=[Depends(require_module(Module.FORM_FILLER.value))],
)

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


async def _read_uploads(
    source_mode: SourceMode,
    files: list[UploadFile] | None,
) -> list[tuple[bytes, str]]:
    """업로드 파일을 (bytes, filename) 목록으로 읽는다(파일 수/크기 가드 적용).

    generate/regenerate_section/review 가 공유하는 멀티파트 업로드 읽기 루프.
    source_mode 가 uploaded/both 가 아니면 빈 목록.
    """
    uploaded: list[tuple[bytes, str]] = []
    if source_mode in ("uploaded", "both") and files:
        for f in files[:_MAX_UPLOAD_FILES]:
            data = await f.read()
            if len(data) > _MAX_UPLOAD_BYTES:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail=f"파일이 너무 큽니다(최대 20MB): {f.filename}",
                )
            uploaded.append((data, f.filename or "업로드"))
    return uploaded


async def _persist_generate_job(
    db: AsyncSession,
    user: User,
    source_mode: SourceMode,
    doc,
) -> None:
    """성공한 문서 생성을 form_jobs(kind='generate')에 best-effort 영속화.

    비용·토큰 회계는 부차적이므로, 영속화 실패가 사용자의 생성 응답을 막지 않도록
    try/except 로 감싸 로그만 남긴다(문서가 본 product, 회계는 best-effort).
    """
    try:
        job = FormJob(
            id=uuid.uuid4(),
            kind="generate",
            source_mode=source_mode,
            template_id=None,  # generate 잡은 양식 없음(nullable).
            user_id=user.id,
            department=user.department,
            status="completed",  # 동기 단일호출 — 성공 시 바로 completed.
            cost_usd=Decimal(str(doc.cost_usd)),
            total_tokens_in=doc.input_tokens,
            total_tokens_out=doc.output_tokens,
            langfuse_trace_id=doc.trace_id,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(job)
        await db.commit()
    except Exception:  # noqa: BLE001 - 회계 영속화 실패가 생성 응답을 막아선 안 됨
        logger.exception("docgen 잡 영속화 실패 — 생성 응답은 정상 반환")
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass


async def _persist_document(
    db: AsyncSession,
    user: User,
    *,
    title: str,
    topic: str | None,
    doc_type: str | None,
    source_mode: SourceMode,
    sections: list[dict],
    sources: list[dict],
    model: str | None,
) -> str | None:
    """생성된 문서를 docgen_documents 에 사용자별 영속화(재열람용).

    문서가 본 product 이므로 영속화 실패가 생성 응답을 막아선 안 된다.
    실패 시 로그만 남기고 None 반환(_persist_generate_job 패턴).
    반환: 저장된 문서 id(str) 또는 None.
    """
    try:
        doc_id = uuid.uuid4()
        row = DocgenDocument(
            id=doc_id,
            user_id=user.id,
            department=user.department,
            title=title[:300] or "(제목 없음)",
            topic=topic,
            doc_type=doc_type,
            source_mode=source_mode,
            sections=sections,
            sources=sources,
            model=model,
        )
        db.add(row)
        await db.commit()
        # 커밋 후 expire 로 row.id 접근 시 lazy refresh 가 날 수 있어 미리 잡은 값 사용.
        return str(doc_id)
    except Exception:  # noqa: BLE001 - 영속화 실패가 생성 응답을 막아선 안 됨
        logger.exception("docgen 문서 영속화 실패 — 생성 응답은 정상 반환")
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


async def _fetch_document_or_404(
    db: AsyncSession,
    document_id: uuid.UUID,
    user: User,
) -> DocgenDocument:
    """본인(또는 admin) 문서만 조회. 아니면 404(소유 누설 방지)."""
    row = (
        await db.execute(
            select(DocgenDocument).where(DocgenDocument.id == document_id)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    is_admin = user.role == UserRole.ADMIN.value
    if not is_admin and str(row.user_id) != str(user.id):
        # 소유자 누설 방지 — 403 대신 404.
        raise HTTPException(status_code=404, detail="문서를 찾을 수 없습니다")
    return row


@router.post("/generate", response_model=DocGenResponse)
async def generate(
    topic: str = Form(..., max_length=4000),
    doc_type: DocType = Form("일반"),
    source_mode: SourceMode = Form("rag"),
    limit: int = Form(8, ge=0, le=20),
    auto_review: bool | None = Form(None),
    files: list[UploadFile] | None = File(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocGenResponse:
    """주제 + 출처(NAS RAG / 사용자 업로드 / 둘다) → 제안서/계획서/보고서 초안.

    멀티파트 폼: source_mode 가 uploaded/both 면 files 의 텍스트를 참고자료로 사용.
    auto_review=true 면 초안 생성 후 LLM judge 검수→문제 섹션 재생성 루프를 돈다(비용↑).
    미지정(None)이면 settings.docgen_auto_review 기본값을 따른다.
    """
    if len(topic.strip()) < 2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="작성 요구/주제를 2자 이상 입력하세요",
        )

    uploaded = await _read_uploads(source_mode, files)

    chunks = await collect_sources(
        query=topic, mode=source_mode, uploaded=uploaded, limit=limit
    )

    # 자동 검수→재생성 루프 사용 여부: 요청 플래그 우선, 미지정이면 설정 기본값.
    use_review = settings.docgen_auto_review if auto_review is None else auto_review
    try:
        if use_review:
            doc = await asyncio.to_thread(
                generate_document_reviewed, topic, doc_type, chunks
            )
        else:
            doc = await asyncio.to_thread(
                generate_document, topic, doc_type, chunks
            )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("docgen 생성 실패")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"문서 생성 실패: {exc}",
        ) from exc

    # 출처는 LLM이 실제 인용한 자료(used_sources)만 노출한다. used_sources 가 비면
    # (모델 미반환 등) 검색된 전체 청크로 폴백. 인용 안 한 자료를 출처로 표기하던 문제 수정.
    cited = {p for p in doc.used_sources}
    src_chunks = [c for c in chunks if c.file_path in cited] if cited else chunks
    # path 중복 제거(파일당 최고 점수 1건). 표시용 메타(name/source_type/doc_id)도 함께 보존.
    # 업로드 청크는 file_id="" 이므로 source_type 을 "uploaded" 로 구분한다(sources.py 규약).
    by_path: dict[str, DocSourceRef] = {}
    for c in src_chunks:
        score = float(c.score)
        src_type = "uploaded" if not (c.file_id or "").strip() else "nas"
        existing = by_path.get(c.file_path)
        if existing is None or score > existing.score:
            by_path[c.file_path] = DocSourceRef(
                path=c.file_path,
                score=round(score, 4),
                name=c.file_name or c.file_path,
                source_type=src_type,
                doc_id=(c.file_id or None),
            )

    # 성공한 생성을 잡으로 영속화(비용/토큰 회계). best-effort — 실패해도 응답은 정상.
    await _persist_generate_job(db, user, source_mode, doc)

    section_dicts = [
        {"heading": s["heading"], "body": s["body"]} for s in doc.sections
    ]
    source_refs = list(by_path.values())

    # 생성 문서 자체를 사용자별로 영속화(재열람용). best-effort — 실패해도 응답 정상.
    document_id = await _persist_document(
        db,
        user,
        title=doc.title,
        topic=topic,
        doc_type=doc_type,
        source_mode=source_mode,
        sections=section_dicts,
        sources=[s.model_dump() for s in source_refs],
        model=doc.model,
    )

    # cost_usd 는 응답에서 제외(관리자 전용). 비용은 계산·영속화되지만 일반 사용자에 미노출.
    return DocGenResponse(
        title=doc.title,
        sections=[DocSection(heading=s["heading"], body=s["body"]) for s in doc.sections],
        markdown=render_markdown(doc.title, doc.sections),
        sources=source_refs,
        model=doc.model,
        document_id=document_id,
    )


@router.post("/regenerate_section", response_model=DocSectionRegenResponse)
async def regenerate_section_endpoint(
    topic: str = Form(..., max_length=4000),
    doc_type: DocType = Form("일반"),
    heading: str = Form(..., max_length=200),
    current_body: str = Form(""),
    feedback: str = Form("", max_length=2000),
    source_mode: SourceMode = Form("rag"),
    limit: int = Form(6, ge=0, le=20),
    files: list[UploadFile] | None = File(None),
    user: User = Depends(get_current_user),
) -> DocSectionRegenResponse:
    """초안의 한 섹션만 (수정 요청 반영) 재생성.

    멀티파트 폼: source_mode 가 uploaded/both 면 files 의 텍스트를 참고자료로 사용한다.
    """
    uploaded = await _read_uploads(source_mode, files)
    chunks = await collect_sources(
        query=f"{topic} {heading}",
        mode=source_mode,
        uploaded=uploaded,
        limit=limit,
    )
    try:
        section, _cost, model, _tokens = await asyncio.to_thread(
            regenerate_section,
            topic,
            doc_type,
            heading,
            current_body,
            feedback,
            chunks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("섹션 재생성 실패")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"섹션 재생성 실패: {exc}",
        ) from exc
    # cost 는 응답에서 제외(관리자 전용). 재생성 비용 집계는 v1 미반영(접근 b 후속).
    return DocSectionRegenResponse(
        section=DocSection(heading=section["heading"], body=section["body"]),
        model=model,
    )


@router.post("/review", response_model=DocReviewResponse)
async def review(
    topic: str = Form(..., max_length=4000),
    doc_type: DocType = Form("일반"),
    title: str = Form(..., max_length=200),
    sections_json: str = Form(...),
    source_mode: SourceMode = Form("rag"),
    limit: int = Form(8, ge=0, le=20),
    files: list[UploadFile] | None = File(None),
    user: User = Depends(get_current_user),
) -> DocReviewResponse:
    """생성 초안 품질검증(LLM-as-judge) — 근거성/요구충족/완성도 평가.

    멀티파트 폼: sections 는 객체배열을 못 실으므로 JSON 문자열(sections_json)로 받는다.
    source_mode 가 uploaded/both 면 files 의 텍스트를 참고자료로 사용한다.
    """
    try:
        parsed_sections = TypeAdapter(list[DocSection]).validate_json(sections_json)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"sections_json 파싱 실패: {exc}",
        ) from exc
    if not parsed_sections:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="sections_json 은 1개 이상의 섹션이어야 합니다",
        )
    uploaded = await _read_uploads(source_mode, files)
    chunks = await collect_sources(
        query=topic, mode=source_mode, uploaded=uploaded, limit=limit
    )
    sections = [{"heading": s.heading, "body": s.body} for s in parsed_sections]
    try:
        result, _cost, model, _tokens = await asyncio.to_thread(
            review_document, topic, doc_type, title, sections, chunks
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        logger.exception("문서 검수 실패")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"문서 검수 실패: {exc}",
        ) from exc
    # cost 는 응답에서 제외(관리자 전용).
    return DocReviewResponse(
        overall_score=result["overall_score"],
        summary=result["summary"],
        section_reviews=[DocSectionReview(**r) for r in result["section_reviews"]],
        missing=result["missing"],
        model=model,
    )


@router.post("/render")
async def render(
    body: DocRenderRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """초안(수정 가능) → .docx 스트리밍 다운로드."""
    sections = [{"heading": s.heading, "body": s.body} for s in body.sections]
    try:
        data = await asyncio.to_thread(build_docx, body.title, sections)
    except Exception as exc:  # noqa: BLE001
        logger.exception("docx 렌더 실패")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"docx 렌더 실패: {exc}",
        ) from exc
    # 결과물을 부서별 NAS 폴더에 사본 저장 (best-effort, 실패해도 다운로드 정상).
    try:
        save_to_nas(
            data,
            department=user.department,
            filename=f"{body.title[:60]}.docx",
        )
    except Exception:  # noqa: BLE001 - NAS 저장은 비치명적
        logger.warning("docgen render NAS 사본 저장 실패(무시)", exc_info=True)
    filename = urllib.parse.quote(f"{body.title[:60]}.docx")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=_DOCX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


@router.post("/render_pptx")
async def render_pptx(
    body: DocRenderRequest,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """초안(수정 가능) → .pptx 스트리밍 다운로드."""
    sections = [{"heading": s.heading, "body": s.body} for s in body.sections]
    try:
        data = await asyncio.to_thread(build_pptx, body.title, sections)
    except Exception as exc:  # noqa: BLE001
        logger.exception("pptx 렌더 실패")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"pptx 렌더 실패: {exc}",
        ) from exc
    # 결과물을 부서별 NAS 폴더에 사본 저장 (best-effort, 실패해도 다운로드 정상).
    try:
        save_to_nas(
            data,
            department=user.department,
            filename=f"{body.title[:60]}.pptx",
        )
    except Exception:  # noqa: BLE001 - NAS 저장은 비치명적
        logger.warning("docgen render_pptx NAS 사본 저장 실패(무시)", exc_info=True)
    filename = urllib.parse.quote(f"{body.title[:60]}.pptx")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=_PPTX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )


# ── 내 문서(저장된 생성 결과) ─────────────────────────────────────────────


@router.get("/documents", response_model=list[DocgenDocumentBrief])
async def list_documents(
    q: str | None = Query(default=None, description="제목/주제 ILIKE 검색"),
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DocgenDocumentBrief]:
    """본인이 저장한 생성 문서 목록(최신순). q 가 있으면 title/topic ILIKE 매칭."""
    stmt = select(DocgenDocument).where(DocgenDocument.user_id == user.id)
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where(
            DocgenDocument.title.ilike(pattern)
            | DocgenDocument.topic.ilike(pattern)
        )
    stmt = stmt.order_by(DocgenDocument.created_at.desc()).limit(limit)
    rows = (await db.execute(stmt)).scalars().all()
    return [
        DocgenDocumentBrief(
            id=str(r.id),
            title=r.title,
            doc_type=r.doc_type,
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/documents/{document_id}", response_model=DocgenDocumentDetail)
async def get_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocgenDocumentDetail:
    """저장된 문서 1건 전체(재열람용 — 섹션/출처 포함)."""
    row = await _fetch_document_or_404(db, document_id, user)
    sections = [
        DocSection(heading=s.get("heading", ""), body=s.get("body", ""))
        for s in (row.sections or [])
    ]
    sources = [DocSourceRef(**s) for s in (row.sources or [])]
    return DocgenDocumentDetail(
        id=str(row.id),
        title=row.title,
        sections=sections,
        sources=sources,
        topic=row.topic,
        doc_type=row.doc_type,
        source_mode=row.source_mode,
        created_at=row.created_at,
    )


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """본인 문서 삭제."""
    row = await _fetch_document_or_404(db, document_id, user)
    await db.delete(row)
    await db.commit()
