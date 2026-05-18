"""세션 검수 라우터 (T9 Phase C).

Phase C 엔드포인트:
| 메서드 | 경로                                              | 설명                       |
|--------|---------------------------------------------------|----------------------------|
| GET    | /api/distribution/sessions                        | 세션 목록 (status 필터)    |
| GET    | /api/distribution/sessions/{id}                   | 세션 상세 + 메시지         |
| PATCH  | /api/distribution/messages/{id}                   | 메시지 편집                |
| POST   | /api/distribution/sessions/{id}/approve           | 세션 승인                  |
| POST   | /api/distribution/sessions/{id}/reject            | 세션 거부                  |
| POST   | /api/distribution/sessions/{id}/send-now          | 즉시 송신 (동기)           |

설계:
- prefix 는 Phase A 라우터(``distribution.py``)와 동일한 ``/api/distribution`` 유지.
  FastAPI 는 경로별 매칭이므로 prefix 공유는 충돌 없음. 코드 분리는 책임 분리 목적.
- ``main.py`` 에서 별도 ``include_router`` 호출 필요.
- 라우터 전체 ``require_admin`` 게이트.
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.user import User
from app.schemas.distribution_sessions import (
    ApproveRequest,
    MessageEditRequest,
    MessageItem,
    RejectRequest,
    SendNowResult,
    SessionDetail,
    SessionListItem,
    SessionStatus,
)
from app.services.distribution import session_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/distribution",
    tags=["distribution-sessions"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# 세션 목록 / 상세
# ---------------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions(
    status_filter: SessionStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
) -> dict[str, list[SessionListItem]]:
    """세션 목록.

    Query params:
    - ``status``: pending/approved/rejected/sending/sent/failed (선택).
    - ``limit``: 1~200, 기본 50.
    - ``offset``: 0 이상.
    """
    items = await session_service.list_sessions(
        db,
        status_filter=status_filter,
        limit=limit,
        offset=offset,
    )
    return {"items": items}


@router.get("/sessions/{session_id}")
async def get_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SessionDetail:
    """세션 상세 + 메시지 리스트."""
    detail = await session_service.get_session_detail(db, session_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="세션 없음"
        )
    return detail


# ---------------------------------------------------------------------------
# 메시지 편집
# ---------------------------------------------------------------------------


@router.patch("/messages/{message_id}")
async def edit_message(
    message_id: UUID,
    payload: MessageEditRequest,
    db: AsyncSession = Depends(get_db),
) -> MessageItem:
    """메시지 편집 — edited_content 저장 + user_edited=True.

    이미 송신된 메시지는 422 반환.
    """
    try:
        updated = await session_service.update_message(
            db,
            message_id,
            edited_content=payload.edited_content,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="메시지 없음"
        )
    return updated


# ---------------------------------------------------------------------------
# 승인 / 거부
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/approve")
async def approve_session(
    session_id: UUID,
    payload: ApproveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, str]:
    """세션 승인 — status='approved', approved_by/at 기록.

    ``status='pending'`` 만 승인 가능. 다른 상태면 409.
    """
    try:
        session_obj = await session_service.approve_session(
            db,
            session_id,
            user_id=current_user.id,
            scheduled_start=payload.scheduled_start,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if session_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="세션 없음"
        )
    return {"status": session_obj.status, "id": str(session_obj.id)}


@router.post("/sessions/{session_id}/reject")
async def reject_session(
    session_id: UUID,
    payload: RejectRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """세션 거부 — status='rejected'. 이유는 로그에만 기록 (DB 컬럼 없음)."""
    try:
        session_obj = await session_service.reject_session(
            db,
            session_id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    if session_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="세션 없음"
        )
    return {"status": session_obj.status, "id": str(session_obj.id)}


# ---------------------------------------------------------------------------
# 즉시 송신
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/send-now")
async def send_session_now(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> SendNowResult:
    """승인된 세션을 즉시 동기 송신.

    응답:
    - 200: 전체 성공 또는 부분 성공.
    - 404: 세션 없음.
    - 409: status='approved' 아님.
    - 500: Telethon/세션 오류 (자격증명/api_hash 는 응답·로그에 노출 X).

    UI 가 호출하므로 대기 시간(``send_after_sec``)은 30초 cap 적용.
    """
    try:
        session_obj, sent_count, failed_count = await session_service.send_session_now(
            db, session_id
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    except Exception as exc:
        # 내부 예외 상세는 서버 로그에만. 클라이언트엔 고정 메시지.
        logger.exception("send-now 예외 — session=%s", session_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="송신 중 오류가 발생했습니다. 서버 로그를 확인하세요.",
        ) from exc

    return SendNowResult(
        session_id=session_obj.id,
        status=session_obj.status,  # type: ignore[arg-type]
        sent_count=sent_count,
        failed_count=failed_count,
        error=None,
    )
