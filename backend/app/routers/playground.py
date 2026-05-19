"""AI Playground 라우터 (T8 Phase 1).

엔드포인트:
| 메서드 | 경로                                            | 설명                          |
|--------|-------------------------------------------------|-------------------------------|
| GET    | /api/playground/providers                       | provider/모델 chip 메타       |
| POST   | /api/playground/sessions                        | 빈 세션 생성                  |
| GET    | /api/playground/sessions                        | 본인 세션 목록 (최신순)       |
| GET    | /api/playground/sessions/{id}/messages          | 세션 메시지 전체              |
| DELETE /api/playground/sessions/{id}            | 본인 세션 hard delete         |
| POST   | /api/playground/chat                            | SSE 스트리밍 채팅             |

권한: ``require_admin`` — Phase 1 은 admin only (T8 PRD 7절).
SSE:
- ``text/event-stream`` + ``data: {json}\\n\\n`` 형식.
- 마지막에 final usage chunk + done 이벤트를 보낸다.
- assistant 메시지 DB 저장은 stream 끝난 후 (메트릭 포함).
"""
from __future__ import annotations

import json
import logging
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import require_admin
from app.models.playground import PlaygroundMessage, PlaygroundSession
from app.models.user import User
from app.schemas.playground import (
    PlaygroundChatRequest,
    PlaygroundImageRequest,
    PlaygroundMediaModelOption,
    PlaygroundMessageOut,
    PlaygroundProviderMeta,
    PlaygroundSessionCreate,
    PlaygroundSessionOut,
    PlaygroundTaskCreated,
    PlaygroundTaskStatus,
    PlaygroundVideoRequest,
)
from app.services.playground import (
    PROVIDER_CHIPS,
    append_message,
    create_session,
    list_sessions,
    stream_chat,
    update_metrics,
)
from app.services.playground.session_manager import mask_request_payload
from app.services.playground.tencent_aigc_media import (
    IMAGE_MODELS,
    VIDEO_MODELS,
    create_image_task,
    create_video_task,
    describe_image_task,
    describe_video_task,
    parse_model_key,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/playground",
    tags=["playground"],
    dependencies=[Depends(require_admin)],
)


# ---------------------------------------------------------------------------
# GET /providers — UI 변형 chip 메타
# ---------------------------------------------------------------------------


@router.get("/providers", response_model=list[PlaygroundProviderMeta])
async def get_providers() -> list[PlaygroundProviderMeta]:
    """Provider 카드 + 모델 변형 chip 목록.

    Phase 1: Tencent AIGC carrier 1개 + Claude Haiku/Sonnet/Opus chip 3개.
    Phase 3 에서 같은 carrier 하위에 GPT/Gemini/... chip 그룹 추가.
    """
    return [PlaygroundProviderMeta.model_validate(p) for p in PROVIDER_CHIPS]


# ---------------------------------------------------------------------------
# POST /sessions — 빈 세션 생성
# ---------------------------------------------------------------------------


@router.post(
    "/sessions",
    response_model=PlaygroundSessionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_session_endpoint(
    body: PlaygroundSessionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> PlaygroundSessionOut:
    row = await create_session(
        db,
        user_id=user.id,
        provider=body.provider,
        model=body.model,
        title=body.title,
        system_prompt=body.system_prompt,
        temperature=body.temperature,
    )
    return PlaygroundSessionOut.model_validate(row)


# ---------------------------------------------------------------------------
# GET /sessions — 본인 세션 목록
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=list[PlaygroundSessionOut])
async def list_sessions_endpoint(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> list[PlaygroundSessionOut]:
    rows = await list_sessions(db, user_id=user.id)
    return [PlaygroundSessionOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# GET /sessions/{id}/messages — 세션 메시지 전체
# ---------------------------------------------------------------------------


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[PlaygroundMessageOut],
)
async def list_messages_endpoint(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> list[PlaygroundMessageOut]:
    session = await _fetch_session_or_404(db, session_id, user)
    stmt = (
        select(PlaygroundMessage)
        .where(PlaygroundMessage.session_id == session.id)
        .order_by(PlaygroundMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()
    return [PlaygroundMessageOut.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# DELETE /sessions/{id} — hard delete (CASCADE 로 메시지/미디어 동반 삭제)
# ---------------------------------------------------------------------------


@router.delete(
    "/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_session_endpoint(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> None:
    session = await _fetch_session_or_404(db, session_id, user)
    await db.delete(session)
    await db.commit()


# ---------------------------------------------------------------------------
# POST /chat — SSE 스트리밍
# ---------------------------------------------------------------------------


@router.post("/chat")
async def chat_endpoint(
    body: PlaygroundChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_admin),
) -> StreamingResponse:
    """SSE 스트리밍 채팅.

    흐름:
    1. session_id 없으면 새 세션 생성.
    2. user 메시지 DB 저장.
    3. 세션 메시지 전체 (user 포함) 를 컨텍스트로 모아 Tencent AIGC stream 호출.
    4. assistant placeholder 메시지 저장 → text_delta 받을 때마다 buffer 누적.
    5. 스트림 종료 후 buffer + 메트릭으로 assistant 메시지 update.
    6. 각 chunk 를 ``data: {json}\\n\\n`` 형식으로 yield.
    """
    # 1. 세션 확보 (없으면 생성).
    if body.session_id is None:
        session = await create_session(
            db,
            user_id=user.id,
            provider=body.provider,
            model=body.model,
            system_prompt=body.system_prompt,
            temperature=body.temperature,
        )
    else:
        session = await _fetch_session_or_404(db, body.session_id, user)

    # 2. user 메시지 저장.
    await append_message(
        db,
        session_id=session.id,
        role="user",
        content=body.message,
    )

    # 3. 세션 메시지 전체 컨텍스트 (user 포함, system 제외 — system 은 별도 인자).
    stmt = (
        select(PlaygroundMessage)
        .where(PlaygroundMessage.session_id == session.id)
        .order_by(PlaygroundMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    history = result.scalars().all()
    api_messages = [
        {"role": m.role, "content": m.content}
        for m in history
        if m.role in ("user", "assistant")
    ]

    # 4. assistant placeholder 메시지 — 메트릭 마스킹된 raw_request 와 함께.
    raw_request = mask_request_payload(
        {
            "model": body.model,
            "temperature": body.temperature,
            "system_prompt": body.system_prompt,
            "message_count": len(api_messages),
            # 헤더는 SDK 내부에서 처리되지만 형식상 마스킹 슬롯 포함.
            "headers": {"Authorization": "***masked***"},
        }
    )
    assistant_msg = await append_message(
        db,
        session_id=session.id,
        role="assistant",
        content="",
        model=body.model,
        raw_request=raw_request,
    )

    # 5. SSE 스트리머.
    async def event_gen():
        buffer: list[str] = []
        usage: dict[str, int] = {}
        start = time.perf_counter()
        try:
            async for chunk in stream_chat(
                messages=api_messages,
                model=body.model,
                system_prompt=session.system_prompt or body.system_prompt,
                temperature=float(session.temperature)
                if session.temperature is not None
                else body.temperature,
            ):
                if chunk["type"] == "text_delta":
                    buffer.append(chunk["delta"])
                elif chunk["type"] == "usage":
                    # 최신 usage 로 덮어쓰기 (final_message 보강이 마지막에 옴).
                    usage = {
                        k: v for k, v in chunk.items() if k != "type"
                    }
                elif chunk["type"] == "error":
                    logger.warning(
                        "playground stream error: %s", chunk.get("message")
                    )
                # 모든 chunk 를 그대로 SSE 로 전달 — UI 가 type 별로 처리.
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        finally:
            # 6. 메트릭 백필. 스트림이 중간에 끊겨도 최선의 메트릭 저장.
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            full_text = "".join(buffer)
            input_tok = usage.get("input_tokens")
            output_tok = usage.get("output_tokens")
            cache_read = usage.get("cache_read_input_tokens", 0) or 0
            cache_create = usage.get("cache_creation_input_tokens", 0) or 0
            cached_total = cache_read + cache_create if usage else None
            await update_metrics(
                db,
                message_id=assistant_msg.id,
                content=full_text,
                input_tokens=input_tok,
                output_tokens=output_tok,
                cached_tokens=cached_total,
                latency_ms=elapsed_ms,
                raw_response=usage or None,
            )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            # nginx/프록시 버퍼링 회피.
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Image / Video task — Phase 4/5 뼈대
# ---------------------------------------------------------------------------


@router.get("/media-models")
async def list_media_models() -> dict[str, list[PlaygroundMediaModelOption]]:
    """이미지/영상 모델 카탈로그 (UI chip 노출용)."""
    return {
        "image": [
            PlaygroundMediaModelOption(key=m["key"], label=m["label"], badge=m["badge"] or None)
            for m in IMAGE_MODELS
        ],
        "video": [
            PlaygroundMediaModelOption(key=m["key"], label=m["label"], badge=m["badge"] or None)
            for m in VIDEO_MODELS
        ],
    }


@router.post("/image", response_model=PlaygroundTaskCreated)
async def create_image_task_endpoint(
    body: PlaygroundImageRequest,
) -> PlaygroundTaskCreated:
    """이미지 생성 task 생성 (비동기). 반환된 task_id 로 폴링."""
    try:
        name, version = parse_model_key(body.model_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        resp = await create_image_task(
            prompt=body.prompt,
            model_name=name,
            model_version=version,
            negative_prompt=body.negative_prompt,
            aspect_ratio=body.aspect_ratio,
            enhance_prompt=body.enhance_prompt,
        )
    except RuntimeError as exc:
        logger.warning("create_image_task 실패: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    task_id = resp.get("TaskId")
    if not task_id:
        raise HTTPException(
            status_code=502, detail=f"텐센트 응답에 TaskId 없음: {resp}"
        )
    return PlaygroundTaskCreated(
        task_id=str(task_id),
        request_id=resp.get("RequestId"),
        kind="image",
    )


@router.post("/video", response_model=PlaygroundTaskCreated)
async def create_video_task_endpoint(
    body: PlaygroundVideoRequest,
) -> PlaygroundTaskCreated:
    """영상 생성 task 생성 (비동기). 반환된 task_id 로 폴링."""
    try:
        name, version = parse_model_key(body.model_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        resp = await create_video_task(
            prompt=body.prompt,
            model_name=name,
            model_version=version,
            duration=body.duration,
            resolution=body.resolution,
            aspect_ratio=body.aspect_ratio,
            audio_generation=body.audio_generation,
            enhance_prompt=body.enhance_prompt,
        )
    except RuntimeError as exc:
        logger.warning("create_video_task 실패: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    task_id = resp.get("TaskId")
    if not task_id:
        raise HTTPException(
            status_code=502, detail=f"텐센트 응답에 TaskId 없음: {resp}"
        )
    return PlaygroundTaskCreated(
        task_id=str(task_id),
        request_id=resp.get("RequestId"),
        kind="video",
    )


@router.get("/tasks/{kind}/{task_id}", response_model=PlaygroundTaskStatus)
async def describe_task_endpoint(kind: str, task_id: str) -> PlaygroundTaskStatus:
    """이미지/영상 task 폴링. kind = "image" | "video".

    텐센트 vod DescribeTaskDetail 응답 구조 (2026-05-19 라이브 probe 확정):
        Status: "PROCESSING" | "FINISH" | "FAIL"
        TaskType: "AigcImageTask" | "AigcVideoTask"
        AigcImageTask / AigcVideoTask: {
            Status, Progress, ErrCode, Message,
            Output: { FileInfos: [{ FileUrl, ExpireTime, MetaData{...} }] }
        }
    """
    if kind not in ("image", "video"):
        raise HTTPException(status_code=400, detail="kind 는 image 또는 video")

    try:
        # describe_task_detail 은 image/video 통합 — kind 와 무관하게 같은 액션.
        resp = await describe_image_task(task_id)
    except RuntimeError as exc:
        logger.warning("describe %s task 실패: %s", kind, exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    # 상위 Status 정규화 (텐센트: PROCESSING / FINISH / FAIL).
    raw_status = str(resp.get("Status") or "").upper()
    if raw_status == "FINISH":
        status_norm = "succeeded"
    elif raw_status == "FAIL":
        status_norm = "failed"
    elif raw_status == "PROCESSING":
        status_norm = "running"
    elif raw_status in {"PENDING", "WAITING", "QUEUED"}:
        status_norm = "pending"
    else:
        status_norm = "unknown"

    # 결과 URL 추출 — TaskType 에 따라 AigcImageTask / AigcVideoTask 키 안의 Output.FileInfos[0].FileUrl
    inner_key = "AigcImageTask" if kind == "image" else "AigcVideoTask"
    inner = resp.get(inner_key) or {}
    output_url: str | None = None
    error_message: str | None = None
    if isinstance(inner, dict):
        file_infos = (inner.get("Output") or {}).get("FileInfos") or []
        if file_infos:
            output_url = file_infos[0].get("FileUrl")
        # ErrCode != 0 이면 실패. Message 가 있으면 사용자에게 노출.
        err_code = inner.get("ErrCode")
        msg = inner.get("Message")
        if err_code and err_code != 0:
            status_norm = "failed"
            error_message = msg or f"ErrCode={err_code}"

    return PlaygroundTaskStatus(
        task_id=task_id,
        kind=kind,
        status=status_norm,
        output_url=output_url,
        error_message=error_message,
        raw=resp,
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _fetch_session_or_404(
    db: AsyncSession,
    session_id: uuid.UUID,
    user: User,
) -> PlaygroundSession:
    """세션 조회 + 소유권 체크. admin only 라우터이지만 본인 세션만 다루는 게 일관성 유지."""
    stmt = select(PlaygroundSession).where(PlaygroundSession.id == session_id)
    result = await db.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="세션을 찾을 수 없습니다"
        )
    # admin only 라도 다른 사용자 세션 침범은 차단.
    if str(row.user_id) != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="다른 사용자의 세션에 접근할 수 없습니다",
        )
    return row
