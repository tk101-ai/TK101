"""체험단 후기 중→한 번역 라우터 (업무개선요구사항 #17).

엔드포인트:
| 메서드 | 경로                                     | 설명                          |
|--------|------------------------------------------|-------------------------------|
| POST   | /api/review-translations/translate       | 번역 후 저장 (Haiku 호출)     |
| GET    | /api/review-translations                 | 목록 (페이지네이션 + 검색)    |
| GET    | /api/review-translations/{id}            | 단건 조회                     |
| PUT    | /api/review-translations/{id}            | 번역문/메타 수정              |
| DELETE | /api/review-translations/{id}            | 삭제                          |

권한: `require_module("review_translation")` — admin + marketing_1.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_module
from app.models.review_translation import ReviewTranslation
from app.models.user import User
from app.modules.constants import Module, UserRole
from app.schemas.review_translation import (
    ReviewTranslationCreate,
    ReviewTranslationList,
    ReviewTranslationRead,
    ReviewTranslationUpdate,
)
from app.services.translation.translator import (
    RateLimitExceeded,
    check_rate_limit,
    translate_chinese_to_korean,
)

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/review-translations",
    tags=["review-translation"],
    dependencies=[Depends(require_module(Module.REVIEW_TRANSLATION.value))],
)


# ---------------------------------------------------------------------------
# POST /translate — 번역 후 저장
# ---------------------------------------------------------------------------


@router.post(
    "/translate",
    response_model=ReviewTranslationRead,
    status_code=status.HTTP_201_CREATED,
)
async def translate_and_save(
    body: ReviewTranslationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReviewTranslationRead:
    """중국어 원문을 한국어로 번역한 뒤 DB에 저장.

    실패 시:
    - ANTHROPIC_API_KEY 미설정: 503
    - 분당 호출 한도 초과: 429 (사용자별 30회/분)
    - SDK/API 오류 (401, 429 등): 502
    - 원문 비어있음: 422 (Pydantic 단에서 차단)
    """
    # H-C2: 사용자별 분당 30회 레이트리밋 (Anthropic 비용 폭주 방지).
    # 인메모리 카운터 + 60초 TTL — slowapi 도입 회피, 단일 인스턴스 운영 전제.
    try:
        check_rate_limit(str(user.id))
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="요청이 너무 잦습니다. 잠시 후 다시 시도하세요.",
        ) from exc

    try:
        # H-C4: translator는 이제 LLMResponse 객체를 그대로 반환.
        result = await asyncio.to_thread(
            translate_chinese_to_korean,
            body.source_text,
            model="haiku",
            user_id=str(user.id),
        )
    except RuntimeError as exc:
        # API 키 미설정 or SDK 미설치.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        # 빈 응답 등 의미적 오류.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except Exception as exc:  # noqa: BLE001 — 외부 API 호출 실패는 502로 정규화.
        logger.exception("Claude 번역 호출 실패")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"번역 API 호출 실패: {exc}",
        ) from exc

    # H-C3: cost_usd None 가드 — Decimal(str(None))은 InvalidOperation 폭발.
    cost_decimal = (
        Decimal(str(result.cost_usd)) if result.cost_usd is not None else None
    )

    row = ReviewTranslation(
        id=uuid.uuid4(),
        source_text=body.source_text,
        translated_text=result.text,
        campaign=body.campaign,
        reviewer_name=body.reviewer_name,
        platform=body.platform,
        model_used=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=cost_decimal,
        created_by_id=user.id,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return ReviewTranslationRead.model_validate(row)


# ---------------------------------------------------------------------------
# GET / — 목록 (페이지네이션 + 검색)
# ---------------------------------------------------------------------------


@router.get("", response_model=ReviewTranslationList)
async def list_translations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, description="원문/번역문 부분 일치"),
    campaign: str | None = Query(default=None, description="캠페인명 정확 일치"),
    db: AsyncSession = Depends(get_db),
) -> ReviewTranslationList:
    stmt = select(ReviewTranslation)
    count_stmt = select(func.count()).select_from(ReviewTranslation)

    if search:
        like = f"%{search}%"
        cond = or_(
            ReviewTranslation.source_text.ilike(like),
            ReviewTranslation.translated_text.ilike(like),
            ReviewTranslation.reviewer_name.ilike(like),
        )
        stmt = stmt.where(cond)
        count_stmt = count_stmt.where(cond)
    if campaign:
        stmt = stmt.where(ReviewTranslation.campaign == campaign)
        count_stmt = count_stmt.where(ReviewTranslation.campaign == campaign)

    total_result = await db.execute(count_stmt)
    total = int(total_result.scalar_one() or 0)

    stmt = (
        stmt.order_by(ReviewTranslation.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    items = [ReviewTranslationRead.model_validate(r) for r in rows]
    return ReviewTranslationList(items=items, total=total, page=page, page_size=page_size)


# ---------------------------------------------------------------------------
# GET /{id}
# ---------------------------------------------------------------------------


@router.get("/{translation_id}", response_model=ReviewTranslationRead)
async def get_translation(
    translation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReviewTranslationRead:
    # H-C1: 본인 자료 또는 admin만 단건 조회. (LIST는 별도 정책으로 후속 처리)
    row = await _fetch_or_404(db, translation_id, requesting_user=user, for_write=False)
    return ReviewTranslationRead.model_validate(row)


# ---------------------------------------------------------------------------
# PUT /{id} — 번역문/메타 수정
# ---------------------------------------------------------------------------


@router.put("/{translation_id}", response_model=ReviewTranslationRead)
async def update_translation(
    translation_id: uuid.UUID,
    body: ReviewTranslationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> ReviewTranslationRead:
    # H-C1: 본인 자료 또는 admin만 수정 가능.
    row = await _fetch_or_404(db, translation_id, requesting_user=user, for_write=True)
    if body.translated_text is not None:
        row.translated_text = body.translated_text
    if body.campaign is not None:
        row.campaign = body.campaign
    if body.reviewer_name is not None:
        row.reviewer_name = body.reviewer_name
    if body.platform is not None:
        row.platform = body.platform
    await db.commit()
    await db.refresh(row)
    return ReviewTranslationRead.model_validate(row)


# ---------------------------------------------------------------------------
# DELETE /{id}
# ---------------------------------------------------------------------------


@router.delete("/{translation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_translation(
    translation_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> None:
    # H-C1: 본인 자료 또는 admin만 삭제 가능.
    row = await _fetch_or_404(db, translation_id, requesting_user=user, for_write=True)
    await db.delete(row)
    await db.commit()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _fetch_or_404(
    db: AsyncSession,
    translation_id: uuid.UUID,
    *,
    requesting_user: User,
    for_write: bool = False,
) -> ReviewTranslation:
    """단건 조회 + 소유권 체크.

    Args:
        db: 비동기 세션.
        translation_id: 조회 대상 ID.
        requesting_user: 요청자. 본인 자료(created_by_id == requesting_user.id)
            또는 admin이 아니면 403.
        for_write: 로깅/감사 컨텍스트 표시용. 정책은 동일 (본인 또는 admin).
            추후 read-only viewer 같은 역할이 생기면 이 플래그로 분기.
    """
    stmt = select(ReviewTranslation).where(ReviewTranslation.id == translation_id)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="번역 기록 없음"
        )
    # admin은 모든 자료 접근 가능. 그 외는 본인 자료만.
    is_admin = requesting_user.role == UserRole.ADMIN.value
    is_owner = (
        row.created_by_id is not None
        and str(row.created_by_id) == str(requesting_user.id)
    )
    if not (is_admin or is_owner):
        action = "수정/삭제" if for_write else "조회"
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"다른 사용자의 번역 기록 {action} 권한 없음",
        )
    return row
