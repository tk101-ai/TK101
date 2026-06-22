"""세션 검수/송신 서비스 (T9 Phase C).

흐름:
- list_sessions(status_filter, limit, offset) → 페이지네이션 목록 (scenario/persona join).
- get_session_detail(id) → 세션 + 모든 메시지 (sender label 채워서).
- update_message(message_id, edited_content) → user_edited=True, status 유지.
- approve_session(id, user_id, scheduled_start?) → status='approved' + approved_by/at 기록.
- reject_session(id, reason?) → status='rejected'.
- send_session_now(id) → 동기 송신 (Telethon 두 client 오픈 후 메시지 순회 송신).

송신 로직은 ``live_test.py`` 의 ``_open_telethon_client`` / ``_resolve_peer`` 를 그대로 재사용.
CLI 흐름과 차이는 단 하나 — UI 트리거이므로 사용자 input() 확인 단계가 없고,
시간차(``send_after_sec``)는 30초 cap 으로 제한 (UI 가 동기로 기다리므로 길게 잡을 수 없음).

[리팩토링 노트] 원본 단일 모듈 ``session_service.py`` (997줄) 를 동작 보존 패키지로
분할. 공개 import 경로 (``from app.services.distribution.session_service import <name>``)
는 그대로 유지하기 위해 모든 공개 이름을 여기서 재노출한다.
- _common: 상수 / ORM→API 변환 / serialize_message / _get_session
- crud: 목록·상세·메시지 편집/추가/삭제·수동 세션·승인/거부
- scheduling: schedule_session_messages
- sending: peer/target 해석·그룹 대화 탐색·_deliver_message
- send_now: send_session_now
"""
from __future__ import annotations

# live_test 재노출 (원본 모듈 네임스페이스에 존재했으므로 그대로 유지 —
# send_worker 가 session_service 에서 _open_telethon_client 를 import 함).
from app.services.distribution.live_test import (
    _open_telethon_client,
    _resolve_peer,
)

from ._common import (
    _CAPTION_MAX_LEN,
    _DELIVER_FAIL,
    _DELIVER_OK,
    _EDITABLE_SESSION_STATUS,
    _MANUAL_SCENARIO_NAME,
    _SEND_NOW_DELAY_CAP_SEC,
    _TYPING_CAP_SEC,
    _build_message_item,
    _build_session_list_item,
    _get_session,
    logger,
    serialize_message,
)
from .crud import (
    _get_or_create_manual_scenario,
    add_message,
    approve_session,
    create_manual_session,
    delete_message,
    get_session_detail,
    list_sessions,
    reject_session,
    update_message,
)
from .scheduling import schedule_session_messages
from .send_now import send_session_now
from .sending import (
    _deliver_message,
    _parse_chat_id,
    _send_payload,
    _typing_action_for,
    discover_group_dialogs,
    resolve_session_peers,
    resolve_session_targets,
)

__all__ = [
    # 라우터 (distribution_sessions) 공개 API
    "list_sessions",
    "get_session_detail",
    "update_message",
    "create_manual_session",
    "add_message",
    "delete_message",
    "approve_session",
    "reject_session",
    "discover_group_dialogs",
    "send_session_now",
    "serialize_message",
    # 워커 (send_worker) 공유 헬퍼
    "_DELIVER_OK",
    "_deliver_message",
    "_open_telethon_client",
    "resolve_session_targets",
    # 그 외 원본 모듈에 존재하던 공개/내부 이름 (참조 안정성 보존)
    "_resolve_peer",
    "_DELIVER_FAIL",
    "_CAPTION_MAX_LEN",
    "_TYPING_CAP_SEC",
    "_SEND_NOW_DELAY_CAP_SEC",
    "_EDITABLE_SESSION_STATUS",
    "_MANUAL_SCENARIO_NAME",
    "_build_message_item",
    "_build_session_list_item",
    "_get_session",
    "_get_or_create_manual_scenario",
    "schedule_session_messages",
    "resolve_session_peers",
    "_parse_chat_id",
    "_typing_action_for",
    "_send_payload",
    "logger",
]
