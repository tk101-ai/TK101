"""요구 기반 문서 생성 라우터 (T5 확장).

POST /api/docgen/generate  — 주제+NAS RAG → 구조화 초안(마크다운+섹션+출처) 반환.
POST /api/docgen/render    — (수정된) 초안 → .docx 다운로드.

권한: 문서작성 모듈(form_filler) 재사용. LLM/검색은 form_filler 빌딩블록 재사용.
"""
from __future__ import annotations

import asyncio
import io
import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_user, require_module
from app.modules.constants import Module
from app.models.user import User
from app.schemas.docgen import (
    DocGenRequest,
    DocGenResponse,
    DocRenderRequest,
    DocSection,
    DocSourceRef,
)
from app.services.docgen import build_docx, generate_document, render_markdown
from app.services.form_filler import nas_bridge

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/docgen",
    tags=["docgen"],
    dependencies=[Depends(require_module(Module.FORM_FILLER.value))],
)

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


@router.post("/generate", response_model=DocGenResponse)
async def generate(
    body: DocGenRequest,
    user: User = Depends(get_current_user),
) -> DocGenResponse:
    """주제 + (선택)NAS RAG → 제안서/계획서/보고서 초안."""
    chunks = []
    if body.use_nas and body.limit > 0:
        try:
            chunks = await nas_bridge.search_relevant_chunks(query=body.topic, limit=body.limit)
        except RuntimeError as exc:
            # 검색 실패는 생성을 막지 않는다(자료 없이 일반 구조로 작성).
            logger.warning("docgen NAS 검색 실패 — 자료 없이 진행: %s", exc)
            chunks = []

    try:
        doc = await asyncio.to_thread(
            generate_document, body.topic, body.doc_type, chunks
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
    filename = urllib.parse.quote(f"{body.title[:60]}.docx")
    return StreamingResponse(
        io.BytesIO(data),
        media_type=_DOCX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{filename}"},
    )
