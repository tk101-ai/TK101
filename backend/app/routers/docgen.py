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

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_user, require_module
from app.modules.constants import Module
from app.models.user import User
from pydantic import TypeAdapter, ValidationError

from app.schemas.docgen import (
    DocGenResponse,
    DocRenderRequest,
    DocReviewResponse,
    DocSection,
    DocSectionRegenResponse,
    DocSectionReview,
    DocSourceRef,
    DocType,
    SourceMode,
)
from app.services.docgen import (
    build_docx,
    build_pptx,
    generate_document,
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


@router.post("/generate", response_model=DocGenResponse)
async def generate(
    topic: str = Form(..., max_length=4000),
    doc_type: DocType = Form("일반"),
    source_mode: SourceMode = Form("rag"),
    limit: int = Form(8, ge=0, le=20),
    files: list[UploadFile] | None = File(None),
    user: User = Depends(get_current_user),
) -> DocGenResponse:
    """주제 + 출처(NAS RAG / 사용자 업로드 / 둘다) → 제안서/계획서/보고서 초안.

    멀티파트 폼: source_mode 가 uploaded/both 면 files 의 텍스트를 참고자료로 사용.
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

    try:
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
    # path 중복 제거(파일당 최고 점수 1건).
    by_path: dict[str, float] = {}
    for c in src_chunks:
        by_path[c.file_path] = max(by_path.get(c.file_path, 0.0), float(c.score))
    return DocGenResponse(
        title=doc.title,
        sections=[DocSection(heading=s["heading"], body=s["body"]) for s in doc.sections],
        markdown=render_markdown(doc.title, doc.sections),
        sources=[DocSourceRef(path=p, score=round(s, 4)) for p, s in by_path.items()],
        cost_usd=doc.cost_usd,
        model=doc.model,
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
        section, cost, model = await asyncio.to_thread(
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
    return DocSectionRegenResponse(
        section=DocSection(heading=section["heading"], body=section["body"]),
        cost_usd=cost,
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
        result, cost, model = await asyncio.to_thread(
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
    return DocReviewResponse(
        overall_score=result["overall_score"],
        summary=result["summary"],
        section_reviews=[DocSectionReview(**r) for r in result["section_reviews"]],
        missing=result["missing"],
        cost_usd=cost,
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
