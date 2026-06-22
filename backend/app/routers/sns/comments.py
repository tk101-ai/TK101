"""SNS 게시물 댓글 — 수집 / 목록 / LLM 분석(요약) / LLM 번역."""

import logging

from fastapi import Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user
from app.models.sns import SocialPost, SocialPostComment
from app.models.user import User
from app.schemas.sns import (
    CollectCommentsResponse,
    CommentAnalysisResponse,
    CommentRead,
    CommentTranslateResponse,
)
from app.services.sns_collection import collect_comments_for_account
from app.models.sns import SocialAccount

from ._common import enforce_llm_rate_limit, router

logger = logging.getLogger("app.routers.sns")

# ---------------- 게시물 댓글 (collect-comments) ----------------


@router.post(
    "/accounts/{account_id}/collect-comments",
    response_model=CollectCommentsResponse,
)
async def collect_comments(
    account_id: str,
    db: AsyncSession = Depends(get_db),
):
    """단일 계정(소유/관리)의 모든 게시물 댓글 본문을 수집해 저장 (멱등)."""
    result = await db.execute(select(SocialAccount).where(SocialAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="계정을 찾을 수 없습니다")
    return await collect_comments_for_account(db, account)


@router.get(
    "/posts/{post_id}/comments",
    response_model=list[CommentRead],
)
async def list_post_comments(
    post_id: str,
    limit: int = Query(200, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """게시물의 댓글 목록 (오래된→최신)."""
    query = (
        select(SocialPostComment)
        .where(SocialPostComment.post_id == post_id)
        .order_by(SocialPostComment.commented_at.asc().nullslast())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post(
    "/posts/{post_id}/comments/analyze",
    response_model=CommentAnalysisResponse,
)
async def analyze_post_comments(
    post_id: str,
    force: bool = Query(False, description="True면 캐시된 요약이 있어도 다시 분석"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """게시물에 수집된 댓글을 Claude 로 분석/요약 (한국어).

    먼저 댓글 수집이 되어 있어야 한다. ANTHROPIC_API_KEY 필요.
    이미 요약이 저장돼 있으면(force=False) LLM 호출 없이 캐시를 반환한다.
    LLM 비용 폭주 방지를 위해 사용자별 레이트리밋(force는 더 보수적)을 적용한다.
    """
    post = (
        await db.execute(select(SocialPost).where(SocialPost.id == post_id))
    ).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다")

    # 캐시 적중: 저장된 요약이 있고 강제 재분석이 아니면 LLM 비용 없이 반환.
    if not force and post.comment_summary:
        return CommentAnalysisResponse(
            post_id=post.id,
            comment_count=post.comment_count or 0,
            summary=post.comment_summary,
            summary_at=post.comment_summary_at,
        )

    # 여기부터 실제 LLM 호출 — 캐시 미적중일 때만 레이트리밋 소비.
    enforce_llm_rate_limit(str(user.id), force=force)

    rows = await db.execute(
        select(SocialPostComment.text)
        .where(SocialPostComment.post_id == post_id)
        .order_by(SocialPostComment.commented_at.asc().nullslast())
    )
    comments = [r[0] for r in rows.all() if r[0] and r[0].strip()]
    if not comments:
        raise HTTPException(
            status_code=400,
            detail="이 게시물에 수집된 댓글이 없습니다. 먼저 '댓글 수집'을 실행하세요.",
        )
    if not settings.anthropic_api_key:
        raise HTTPException(
            status_code=503, detail="ANTHROPIC_API_KEY 미설정 — 댓글 분석 불가."
        )

    from app.services.sns_collectors.comment_analyzer import analyze_comments

    try:
        summary = await analyze_comments(
            post_title=post.title or "",
            comments=comments,
            comment_count=len(comments),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 — 외부 LLM 호출 실패 격리
        raise HTTPException(status_code=502, detail=f"댓글 분석 실패: {type(exc).__name__}")

    # 요약을 영속화 — 새로고침/드로어 재열람 시 재분석(비용) 방지.
    post.comment_summary = summary
    post.comment_summary_at = func.now()
    await db.commit()
    await db.refresh(post)

    return CommentAnalysisResponse(
        post_id=post.id,
        comment_count=len(comments),
        summary=summary,
        summary_at=post.comment_summary_at,
    )


@router.post(
    "/posts/{post_id}/comments/translate",
    response_model=CommentTranslateResponse,
)
async def translate_post_comments(
    post_id: str,
    force: bool = Query(False, description="True면 이미 번역된 댓글도 다시 번역"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """게시물 댓글을 한국어로 번역(다국어→한국어). 원문은 보존, 번역문만 캐시.

    글로벌 채널 특성상 댓글이 외국어로 달리므로 마케팅 담당자가 읽을 수 있게 번역한다.
    이미 번역된 댓글은 건너뛴다(force=True면 재번역). ANTHROPIC_API_KEY 필요.
    LLM 비용 폭주 방지를 위해 사용자별 레이트리밋(force는 더 보수적)을 적용한다.
    """
    post = (
        await db.execute(select(SocialPost).where(SocialPost.id == post_id))
    ).scalar_one_or_none()
    if post is None:
        raise HTTPException(status_code=404, detail="게시물을 찾을 수 없습니다")
    post_pk = post.id

    rows = await db.execute(
        select(SocialPostComment)
        .where(SocialPostComment.post_id == post_id)
        .order_by(SocialPostComment.commented_at.asc().nullslast())
    )
    all_comments = list(rows.scalars().all())

    # 번역 대상: 원문이 있고, force 거나 아직 미번역인 댓글.
    targets = [
        c
        for c in all_comments
        if (c.text and c.text.strip()) and (force or not c.translated_text)
    ]

    translated_count = 0
    if targets:
        # 실제 LLM 호출이 있을 때만 레이트리밋 소비.
        enforce_llm_rate_limit(str(user.id), force=force)
        if not settings.anthropic_api_key:
            raise HTTPException(
                status_code=503, detail="ANTHROPIC_API_KEY 미설정 — 댓글 번역 불가."
            )
        from app.services.sns_collectors.comment_translator import translate_to_korean

        try:
            results = await translate_to_korean([c.text or "" for c in targets])
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except Exception as exc:  # noqa: BLE001 — 외부 LLM 호출 실패 격리
            raise HTTPException(
                status_code=502, detail=f"댓글 번역 실패: {type(exc).__name__}"
            )
        for comment, translated in zip(targets, results):
            if translated:
                comment.translated_text = translated
                translated_count += 1
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.exception("SNS 댓글 번역 저장 실패")
            raise HTTPException(
                status_code=500, detail=f"번역 저장 실패: {type(exc).__name__}"
            )

    # 번역 반영된 최종 목록 재조회 (commit 후 일관 상태로 반환).
    final = await db.execute(
        select(SocialPostComment)
        .where(SocialPostComment.post_id == post_id)
        .order_by(SocialPostComment.commented_at.asc().nullslast())
    )
    return CommentTranslateResponse(
        post_id=post_pk,
        translated=translated_count,
        comments=list(final.scalars().all()),
    )
