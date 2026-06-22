"""채팅 스트리밍 오케스트레이션.

``routers/playground/chat.py`` 의 HTTP 핸들러에서 분리한 비-HTTP 로직:
세션 확보, 첨부 로드, 히스토리 → API 메시지 변환, NAS RAG 컨텍스트 주입,
LLM SSE 스트리밍 + 사용량/비용 기록.

동작은 기존 ``chat_endpoint`` 와 동일 (순수 리팩토링).
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playground import PlaygroundAttachment, PlaygroundMessage, PlaygroundSession
from app.models.user import User
from app.schemas.playground import PlaygroundChatRequest
from app.services.playground import (
    append_message,
    create_session,
    stream_chat,
    update_metrics,
)
from app.services.playground.attachments import build_user_content
from app.services.playground.nas_rag import (
    build_context_block,
    search_rag_context,
    source_paths,
)
from app.services.playground.pricing import calc_text_cost
from app.services.playground.session_manager import mask_request_payload

logger = logging.getLogger(__name__)


async def _load_attachments_payload(
    db: AsyncSession,
    *,
    attachment_ids: list[uuid.UUID] | None,
    user: User,
    session: PlaygroundSession,
) -> list[dict]:
    """본인 소유 첨부를 로드하고 (미지정 세션이면) 이번 세션에 귀속."""
    attachments_payload: list[dict] = []
    if not attachment_ids:
        return attachments_payload

    att_stmt = select(PlaygroundAttachment).where(
        PlaygroundAttachment.id.in_(attachment_ids),
        PlaygroundAttachment.user_id == user.id,
    )
    att_rows = (await db.execute(att_stmt)).scalars().all()
    if len(att_rows) != len(set(attachment_ids)):
        raise HTTPException(status_code=404, detail="첨부 파일을 찾을 수 없습니다")
    for a in att_rows:
        # 첨부를 이번 세션에 귀속 (재사용 방지 + 감사로그).
        if a.session_id is None:
            a.session_id = session.id
        attachments_payload.append(
            {
                "kind": a.kind,
                "filename": a.filename,
                "mime": a.mime,
                "file_path": a.file_path,
                "extracted_text": a.extracted_text,
            }
        )
    return attachments_payload


def _build_api_messages(
    history: list[PlaygroundMessage],
    *,
    attachments_payload: list[dict],
    model: str,
) -> list[dict]:
    """DB 메시지 히스토리를 LLM API 메시지 리스트로 변환.

    마지막 user 메시지에만 이번 호출의 첨부를 결합.
    """
    api_messages: list[dict] = []
    history_filtered = [m for m in history if m.role in ("user", "assistant")]
    for idx, m in enumerate(history_filtered):
        is_last_user = (
            m.role == "user"
            and idx == len(history_filtered) - 1
            and attachments_payload
        )
        if is_last_user:
            content = build_user_content(
                user_text=m.content,
                attachments=attachments_payload,
                model=model,
            )
            api_messages.append({"role": "user", "content": content})
        else:
            api_messages.append({"role": m.role, "content": m.content})
    return api_messages


async def prepare_chat(
    db: AsyncSession,
    *,
    body: PlaygroundChatRequest,
    user: User,
    fetch_session_or_404: Any,
) -> dict:
    """채팅 SSE 응답에 필요한 모든 컨텍스트를 준비.

    세션 확보, 첨부 로드, user 메시지 저장, 히스토리 → API 메시지 변환,
    NAS RAG 주입, assistant placeholder 생성까지 수행하고 ``event_gen`` 에
    필요한 값을 dict 로 반환한다.
    """
    # 세션 확보 (없으면 생성).
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
        session = await fetch_session_or_404(db, body.session_id, user)

    # 첨부 로드 — 본인 소유 + (세션 미지정이거나 같은 세션) 만 허용.
    attachments_payload = await _load_attachments_payload(
        db,
        attachment_ids=body.attachment_ids,
        user=user,
        session=session,
    )

    # DB 에는 사용자가 입력한 원문만 저장 (이미지·문서 본문은 첨부 row 에 별도 보관).
    await append_message(
        db,
        session_id=session.id,
        role="user",
        content=body.message,
    )

    stmt = (
        select(PlaygroundMessage)
        .where(PlaygroundMessage.session_id == session.id)
        .order_by(PlaygroundMessage.created_at.asc())
    )
    result = await db.execute(stmt)
    history = result.scalars().all()
    api_messages = _build_api_messages(
        history,
        attachments_payload=attachments_payload,
        model=body.model,
    )

    # NAS RAG — 토글이 켜져 있으면 마지막 사용자 메시지로 회사 문서를 검색해
    # system 컨텍스트로 주입. 검색 실패/0건은 일반 채팅으로 graceful 진행.
    base_system_prompt = session.system_prompt or body.system_prompt
    effective_system_prompt = base_system_prompt
    rag_sources: list[str] = []
    if body.use_nas_rag:
        rag_hits = await search_rag_context(body.message)
        if rag_hits:
            rag_sources = source_paths(rag_hits)
            context_block = build_context_block(rag_hits)
            # 컨텍스트를 system prompt 앞에 주입 (기존 system prompt 는 뒤에 보존).
            effective_system_prompt = (
                f"{context_block}\n\n{base_system_prompt}"
                if base_system_prompt
                else context_block
            )

    raw_request = mask_request_payload(
        {
            "model": body.model,
            "temperature": body.temperature,
            "system_prompt": body.system_prompt,
            "message_count": len(api_messages),
            "use_nas_rag": body.use_nas_rag,
            "nas_sources": rag_sources,
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

    return {
        "session": session,
        "api_messages": api_messages,
        "effective_system_prompt": effective_system_prompt,
        "rag_sources": rag_sources,
        "assistant_msg": assistant_msg,
    }


async def stream_chat_events(
    db: AsyncSession,
    *,
    body: PlaygroundChatRequest,
    session: PlaygroundSession,
    api_messages: list[dict],
    effective_system_prompt: str | None,
    rag_sources: list[str],
    assistant_msg: PlaygroundMessage,
) -> AsyncIterator[str]:
    """SSE 이벤트 제너레이터 — 텍스트 델타 흘려보내고 종료 시 사용량/비용 기록."""
    buffer: list[str] = []
    usage: dict[str, int] = {}
    start = time.perf_counter()
    # RAG 출처를 먼저 흘려보내 프론트가 메시지 하단에 표시할 수 있게 한다.
    if rag_sources:
        yield (
            "data: "
            + json.dumps(
                {"type": "sources", "sources": rag_sources},
                ensure_ascii=False,
            )
            + "\n\n"
        )
    try:
        async for chunk in stream_chat(
            messages=api_messages,
            model=body.model,
            system_prompt=effective_system_prompt,
            temperature=float(session.temperature)
            if session.temperature is not None
            else body.temperature,
        ):
            if chunk["type"] == "text_delta":
                buffer.append(chunk["delta"])
            elif chunk["type"] == "usage":
                usage = {k: v for k, v in chunk.items() if k != "type"}
            elif chunk["type"] == "error":
                logger.warning("playground stream error: %s", chunk.get("message"))
            yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
    finally:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        full_text = "".join(buffer)
        input_tok = usage.get("input_tokens")
        output_tok = usage.get("output_tokens")
        cache_read = usage.get("cache_read_input_tokens", 0) or 0
        cache_create = usage.get("cache_creation_input_tokens", 0) or 0
        cached_total = cache_read + cache_create if usage else None
        cost = calc_text_cost(
            model=body.model,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cached_tokens=cached_total,
        )
        await update_metrics(
            db,
            message_id=assistant_msg.id,
            content=full_text,
            input_tokens=input_tok,
            output_tokens=output_tok,
            cached_tokens=cached_total,
            latency_ms=elapsed_ms,
            raw_response=usage or None,
            cost_usd=cost,
        )
