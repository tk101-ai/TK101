"""채팅 (SSE) — 스트리밍 LLM. 무거운 오케스트레이션은 services 로 위임."""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.schemas.playground import PlaygroundChatRequest
from app.services.playground.chat_orchestrator import prepare_chat, stream_chat_events
from app.services.playground.usage_check import check_quota_or_raise

from ._common import fetch_session_or_404, make_subrouter

logger = logging.getLogger(__name__)

router: APIRouter = make_subrouter()


@router.post("/chat")
async def chat_endpoint(
    body: PlaygroundChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    # 한도 초과 체크 — 초과 시 402.
    await check_quota_or_raise(db, user)

    # 준비 단계(NAS RAG 검색·메시지 빌드 등) 실패는 SSE 200 + 에러 이벤트로 graceful
    # 처리한다. 과거: NAS RAG 토글 시 임베딩 콜드로 prepare_chat 가 막혀 500/502 발생.
    try:
        prepared = await prepare_chat(
            db,
            body=body,
            user=user,
            fetch_session_or_404=fetch_session_or_404,
        )
    except HTTPException:
        raise  # 한도/세션 권한 등 의도된 상태코드는 그대로.
    except Exception:
        logger.exception("prepare_chat 실패 — 에러 이벤트로 응답")

        def err_gen():
            yield (
                "data: "
                + json.dumps(
                    {
                        "type": "error",
                        "message": "채팅 준비 중 오류가 발생했습니다. 잠시 후 다시 시도하세요.",
                    },
                    ensure_ascii=False,
                )
                + "\n\n"
            )
            yield "data: " + json.dumps({"type": "done"}, ensure_ascii=False) + "\n\n"

        return StreamingResponse(
            err_gen(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    def event_gen():
        return stream_chat_events(
            db,
            body=body,
            session=prepared["session"],
            api_messages=prepared["api_messages"],
            effective_system_prompt=prepared["effective_system_prompt"],
            rag_sources=prepared["rag_sources"],
            assistant_msg=prepared["assistant_msg"],
        )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
