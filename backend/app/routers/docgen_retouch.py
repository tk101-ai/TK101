"""docgen 리터치 프롬프트(프리셋) 라우터.

생성 문서를 다른 AI 로 재디자인/재생성할 때 쓰는 고품질 프롬프트를 생성하고,
개인 보관함 + 공유 토글(playground 콘텐츠 라이브러리 패턴)로 관리한다.

| 메서드 | 경로                                   | 권한        | 설명                       |
|--------|----------------------------------------|-------------|----------------------------|
| POST   | /api/docgen/retouch-prompt             | 로그인      | 현재 초안→리터치 프롬프트  |
| POST   | /api/docgen/retouch-prompts            | 로그인      | 프리셋 저장                |
| GET    | /api/docgen/retouch-prompts            | 로그인(본인)| 내 프리셋 목록             |
| GET    | /api/docgen/retouch-prompts/shared     | 로그인      | 공유 프리셋(전체)          |
| PATCH  | /api/docgen/retouch-prompts/{id}       | 로그인(본인)| 수정/공유 토글             |
| DELETE | /api/docgen/retouch-prompts/{id}       | 로그인(본인)| 삭제                       |
"""
from __future__ import annotations

import asyncio
import functools
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_module
from app.models.docgen import DocgenRetouchPrompt
from app.models.user import User
from app.modules.constants import Module
from app.schemas.docgen import (
    HtmlDeckOut,
    HtmlDeckRequest,
    RetouchPresetOut,
    RetouchPresetPatchRequest,
    RetouchPresetSaveRequest,
    RetouchPromptOut,
    RetouchPromptRequest,
    SharedRetouchPresetOut,
)
from app.services.docgen.html_deck import generate_html_deck
from app.services.docgen.retouch_prompt import build_retouch_prompt

router = APIRouter(
    prefix="/api/docgen",
    tags=["docgen"],
    dependencies=[Depends(require_module(Module.FORM_FILLER.value))],
)


def _to_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError):
        return None


async def _fetch_preset_or_404(
    db: AsyncSession, preset_id: uuid.UUID, user: User
) -> DocgenRetouchPrompt:
    row = (
        await db.execute(
            select(DocgenRetouchPrompt).where(DocgenRetouchPrompt.id == preset_id)
        )
    ).scalar_one_or_none()
    if row is None or row.user_id != user.id:
        raise HTTPException(status_code=404, detail="프리셋을 찾을 수 없습니다")
    return row


@router.post("/html-deck", response_model=HtmlDeckOut)
async def create_html_deck(
    body: HtmlDeckRequest,
    user: User = Depends(get_current_user),
) -> HtmlDeckOut:
    """디자인 프롬프트 + 현재 콘텐츠 → 자체완결 HTML 슬라이드 덱(디자인 반영).

    python-pptx 고정 렌더러가 못 살리는 임의 디자인을 LLM이 HTML/CSS 로 구현.
    call_claude 는 동기이므로 to_thread 로 호출(요청당 LLM 1콜, 비용 반환).
    """
    html, model, cost = await asyncio.to_thread(
        functools.partial(
            generate_html_deck,
            title=body.title,
            sections=[s.model_dump() for s in body.sections],
            doc_type=body.doc_type,
            design_prompt=body.design_prompt,
        )
    )
    return HtmlDeckOut(html=html, model=model, cost_usd=cost)


@router.post("/retouch-prompt", response_model=RetouchPromptOut)
async def create_retouch_prompt(
    body: RetouchPromptRequest,
    user: User = Depends(get_current_user),
) -> RetouchPromptOut:
    """현재 초안(편집 가능)으로 리터치 프롬프트 생성. 저장은 별도."""
    prompt_text, model, _cost = build_retouch_prompt(
        title=body.title,
        sections=[s.model_dump() for s in body.sections],
        doc_type=body.doc_type,
        topic=body.topic,
        target=body.target,
    )
    return RetouchPromptOut(prompt_text=prompt_text, target=body.target, model=model)


@router.post(
    "/retouch-prompts",
    response_model=RetouchPresetOut,
    status_code=status.HTTP_201_CREATED,
)
async def save_retouch_preset(
    body: RetouchPresetSaveRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RetouchPresetOut:
    """리터치 프롬프트를 프리셋으로 저장(개인 보관함)."""
    row = DocgenRetouchPrompt(
        user_id=user.id,
        department=user.department,
        source_document_id=_to_uuid(body.source_document_id),
        title=body.title,
        doc_type=body.doc_type,
        target=body.target,
        prompt_text=body.prompt_text,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return RetouchPresetOut.model_validate(row)


@router.get("/retouch-prompts", response_model=list[RetouchPresetOut])
async def list_my_retouch_presets(
    q: str | None = Query(default=None, description="제목 부분검색"),
    doc_type: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=300),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[RetouchPresetOut]:
    """본인 프리셋 목록(최신순)."""
    stmt = (
        select(DocgenRetouchPrompt)
        .where(DocgenRetouchPrompt.user_id == user.id)
        .order_by(desc(DocgenRetouchPrompt.created_at))
        .limit(limit)
    )
    if q:
        stmt = stmt.where(DocgenRetouchPrompt.title.ilike(f"%{q}%"))
    if doc_type:
        stmt = stmt.where(DocgenRetouchPrompt.doc_type == doc_type)
    rows = (await db.execute(stmt)).scalars().all()
    return [RetouchPresetOut.model_validate(r) for r in rows]


@router.get("/retouch-prompts/shared", response_model=list[SharedRetouchPresetOut])
async def list_shared_retouch_presets(
    q: str | None = Query(default=None, description="제목 부분검색"),
    doc_type: str | None = Query(default=None),
    limit: int = Query(default=120, ge=1, le=300),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[SharedRetouchPresetOut]:
    """공유 프리셋 — 사용자 전체가 공유한 프리셋(최신 공유순) + 소유자 표기."""
    stmt = (
        select(DocgenRetouchPrompt, User.name, User.department)
        .join(User, User.id == DocgenRetouchPrompt.user_id)
        .where(DocgenRetouchPrompt.is_shared.is_(True))
        .order_by(desc(DocgenRetouchPrompt.shared_at))
        .limit(limit)
    )
    if q:
        stmt = stmt.where(DocgenRetouchPrompt.title.ilike(f"%{q}%"))
    if doc_type:
        stmt = stmt.where(DocgenRetouchPrompt.doc_type == doc_type)

    rows = (await db.execute(stmt)).all()
    out: list[SharedRetouchPresetOut] = []
    for preset, owner_name, owner_dept in rows:
        item = SharedRetouchPresetOut.model_validate(preset)
        item.owner_name = owner_name
        item.owner_department = owner_dept
        item.is_mine = preset.user_id == user.id
        out.append(item)
    return out


@router.patch("/retouch-prompts/{preset_id}", response_model=RetouchPresetOut)
async def patch_retouch_preset(
    preset_id: uuid.UUID,
    body: RetouchPresetPatchRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> RetouchPresetOut:
    """프리셋 수정 — 제목/본문 편집 또는 공유 토글. 소유자만."""
    row = await _fetch_preset_or_404(db, preset_id, user)
    if body.title is not None:
        row.title = body.title
    if body.prompt_text is not None:
        row.prompt_text = body.prompt_text
    if body.is_shared is not None:
        row.is_shared = body.is_shared
        row.shared_at = func.now() if body.is_shared else None
    await db.commit()
    await db.refresh(row)
    return RetouchPresetOut.model_validate(row)


@router.delete(
    "/retouch-prompts/{preset_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_retouch_preset(
    preset_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    """본인 프리셋 삭제."""
    row = await _fetch_preset_or_404(db, preset_id, user)
    await db.delete(row)
    await db.commit()
