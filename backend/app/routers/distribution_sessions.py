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
- 권한 (T9 라우터 가드 정책 통일):
  - 라우터 전체: ``require_module(Module.DISTRIBUTION.value)`` — admin + 신사업팀.
  - send-now (실 텔레그램 송신): endpoint 별 ``require_admin`` 추가.
  - 목록/상세/메시지 편집/승인/거부: 신사업팀 검수 가능.
"""
from __future__ import annotations

import logging
import os
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user, require_admin, require_module
from app.models.distribution import (
    DistributionMessage,
    DistributionPersona,
    DistributionSession,
)
from app.models.user import User
from app.modules.constants import Module
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
from app.services.distribution import attachment_service, session_service

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/distribution",
    tags=["distribution-sessions"],
    dependencies=[Depends(require_module(Module.DISTRIBUTION.value))],
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
    """세션 상세 + 메시지 리스트.

    session_service.get_session_detail 은 헤더에 language 를 채우지 않으므로
    (해당 서비스는 다른 워크스트림 소유라 미수정) 여기서 session.language 를
    한 번 더 조회하여 응답 헤더에 주입한다 (T9 — 2026-05-27).
    """
    detail = await session_service.get_session_detail(db, session_id)
    if detail is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="세션 없음"
        )
    language = (
        await db.execute(
            select(DistributionSession.language).where(
                DistributionSession.id == session_id
            )
        )
    ).scalar_one_or_none()
    if language:
        enriched_header = detail.session.model_copy(update={"language": language})
        return SessionDetail(session=enriched_header, messages=detail.messages)
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
    """메시지 편집 — 본문(edited_content) 또는 송신 텀(send_after_sec) 갱신.

    - 둘 중 하나는 반드시 제공 (둘 다 None 이면 422).
    - 이미 송신된 메시지는 422.
    """
    try:
        updated = await session_service.update_message(
            db,
            message_id,
            edited_content=payload.edited_content,
            send_after_sec=payload.send_after_sec,
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
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    """세션 승인 — status='approved', approved_by/at 기록. 신사업팀 검수 가능.

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
# 세션 삭제 (검수 대기 / 거부 / 실패만)
# ---------------------------------------------------------------------------

# 송신 이력 보호: 보낸/보내는 중/승인(예약) 세션은 삭제 불가.
# 검수 대기(pending) · 거부(rejected) · 생성 실패(failed)만 정리 허용.
_DELETABLE_SESSION_STATUSES = {"pending", "rejected", "failed"}


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """세션 삭제. 메시지·송신로그는 FK ON DELETE CASCADE 로 함께 삭제된다.

    검수 대기/거부/실패 상태만 허용. 그 외(승인/송신중/송신완료)는 409.
    """
    res = await db.execute(
        select(DistributionSession).where(DistributionSession.id == session_id)
    )
    session_obj = res.scalar_one_or_none()
    if session_obj is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="세션 없음"
        )
    if session_obj.status not in _DELETABLE_SESSION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"'{session_obj.status}' 상태 세션은 삭제할 수 없습니다 "
                "(검수 대기 / 거부 / 실패만 삭제 가능)"
            ),
        )
    await db.delete(session_obj)
    await db.commit()
    logger.info("distribution.session: 삭제 id=%s status=%s", session_id, session_obj.status)
    return {"deleted": str(session_id)}


# ---------------------------------------------------------------------------
# 그룹 chat_id 찾기 (3명 방 송신용)
# ---------------------------------------------------------------------------


@router.get("/groups/discover")
async def discover_groups(
    persona_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> dict[str, list[dict]]:
    """지정 페르소나 계정이 참여 중인 그룹 목록 (그룹 chat_id 선택용). **admin only**.

    관리자가 텔레그램에서 3명 방을 개설(2 API 계정 + 본인)한 뒤, 그 계정으로
    그룹을 조회해 chat_id 를 골라 생성 시 group_chat_id 로 사용한다.
    """
    res = await db.execute(
        select(DistributionPersona).where(DistributionPersona.id == persona_id)
    )
    persona = res.scalar_one_or_none()
    if persona is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="페르소나 없음")
    if not (persona.api_id_enc and persona.api_hash_enc):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="이 계정에 텔레그램 자격증명이 없어 그룹을 조회할 수 없습니다.",
        )
    try:
        groups = await session_service.discover_group_dialogs(persona)
    except Exception as exc:  # noqa: BLE001 — 외부 텔레그램 호출 실패 격리
        logger.exception("그룹 조회 실패 — persona=%s", persona_id)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"그룹 조회 실패: {type(exc).__name__}",
        )
    return {"items": groups}


# ---------------------------------------------------------------------------
# 즉시 송신
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/send-now")
async def send_session_now(
    session_id: UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
) -> SendNowResult:
    """승인된 세션을 즉시 동기 송신. **admin only** — 실 텔레그램 송신.

    응답:
    - 200: 전체 성공 또는 부분 성공.
    - 404: 세션 없음.
    - 409: status='approved' 아님.
    - 500: Telethon/세션 오류 (자격증명/api_hash 는 응답·로그에 노출 X).

    UI 가 호출하므로 대기 시간(``send_after_sec``)은 30초 cap 적용.
    """
    try:
        (
            session_obj,
            sent_count,
            failed_count,
            first_error,
        ) = await session_service.send_session_now(db, session_id)
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
        error=first_error,
    )


# ---------------------------------------------------------------------------
# 메시지 첨부 파일 (T9 — 2026-05-26 추가)
# ---------------------------------------------------------------------------


async def _load_message_or_404(
    db: AsyncSession, message_id: UUID
) -> DistributionMessage:
    """편집·첨부 공용 — 메시지 단건 로드. 없으면 404."""
    msg = (
        await db.execute(
            select(DistributionMessage).where(DistributionMessage.id == message_id)
        )
    ).scalar_one_or_none()
    if msg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="메시지 없음"
        )
    return msg


@router.post("/messages/{message_id}/attachment")
async def upload_message_attachment(
    message_id: UUID,
    file: UploadFile = File(...),
    caption: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> MessageItem:
    """메시지에 파일 첨부 (이미지/문서).

    - 이미 송신된 메시지는 422.
    - 동일 메시지에 재업로드 시 기존 파일 덮어쓰기 + DB 메타 갱신.
    - 화이트리스트 외 확장자: 415. 크기 초과: 413.
    """
    msg = await _load_message_or_404(db, message_id)
    if msg.status == "sent":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="이미 송신된 메시지에는 첨부할 수 없습니다.",
        )

    file_bytes = await file.read(
        attachment_service.settings.distribution_attachment_max_bytes + 1
    )
    try:
        saved = attachment_service.save_attachment(
            session_id=msg.session_id,
            message_id=msg.id,
            file_bytes=file_bytes,
            original_filename=file.filename or "attachment",
            content_type=file.content_type,
        )
    except attachment_service.AttachmentError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    # 이전 첨부 파일이 다른 확장자였으면 잔여 파일 정리.
    if msg.attachment_path and msg.attachment_path != saved.path:
        attachment_service.delete_attachment(msg.attachment_path)

    msg.attachment_path = saved.path
    msg.attachment_filename = saved.filename
    msg.attachment_mime = saved.mime
    msg.attachment_kind = saved.kind
    if caption is not None:
        msg.attachment_caption = caption.strip() or None
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    return await session_service.serialize_message(db, msg)


@router.delete("/messages/{message_id}/attachment")
async def delete_message_attachment(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> MessageItem:
    """첨부 파일 제거. 이미 송신된 메시지는 422."""
    msg = await _load_message_or_404(db, message_id)
    if msg.status == "sent":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="이미 송신된 메시지의 첨부는 제거할 수 없습니다.",
        )

    attachment_service.delete_attachment(msg.attachment_path)
    msg.attachment_path = None
    msg.attachment_filename = None
    msg.attachment_mime = None
    msg.attachment_kind = None
    msg.attachment_caption = None
    db.add(msg)
    await db.commit()
    await db.refresh(msg)

    return await session_service.serialize_message(db, msg)


@router.get("/messages/{message_id}/attachment")
async def download_message_attachment(
    message_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> FileResponse:
    """첨부 파일 다운로드/미리보기. 검수 UI 의 ``<img src>`` · 다운로드 링크에서 사용."""
    msg = await _load_message_or_404(db, message_id)
    if not msg.attachment_path:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="첨부 없음"
        )
    if not attachment_service.is_safe_path(msg.attachment_path):
        # DB 가 손상되어 외부 경로가 들어간 비정상 케이스.
        logger.warning("불안전 경로 차단 — message=%s path=%s", msg.id, msg.attachment_path)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="잘못된 첨부 경로"
        )
    if not os.path.isfile(msg.attachment_path):
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="첨부 파일이 사라졌습니다."
        )
    return FileResponse(
        msg.attachment_path,
        media_type=msg.attachment_mime or "application/octet-stream",
        filename=msg.attachment_filename or "attachment",
    )
