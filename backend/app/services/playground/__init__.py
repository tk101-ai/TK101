"""AI Playground 서비스 (T8 Phase 1).

구성:
- ``tencent_aigc_client``: 텐센트 MPaaS AIGC OpenAI-compatible SSE 어댑터 (단일 endpoint, model 분기).
- ``session_manager``: 세션/메시지 DB CRUD.
- ``PROVIDER_CHIPS``: UI 변형 chip 메타. Phase 1 은 Claude 3종, Phase 3 에서 model id 만 추가.

Provider 라우팅 결정 (T8 PRD 3절 수정):
- 텐센트 AIGC endpoint 1개로 8 공급자를 모두 호출. ``provider_key`` 는 항상 ``tencent_aigc``.
- UI 카드는 "공급자"가 아니라 "모델 패밀리" 단위로 그룹핑 (Claude / GPT / Gemini ...) —
  실제 API 호출 시 carrier 는 동일.
"""
from app.services.playground.session_manager import (
    append_message,
    create_session,
    list_sessions,
    update_metrics,
)
from app.services.playground.tencent_aigc_client import (
    MODEL_CLAUDE_HAIKU,
    MODEL_CLAUDE_OPUS,
    MODEL_CLAUDE_SONNET,
    stream_chat,
)

# UI 카드는 "모델 패밀리" 단위로 그룹핑 (텐센트 원본 화면과 동일).
# 실제 API 호출 carrier 는 항상 텐센트 AIGC endpoint 단일.
# Phase 3 에서 openai / gemini / grok / kimi / glm / minimax / deepseek 패밀리를
# 같은 PROVIDER_CHIPS 리스트에 추가만 하면 됨 (carrier 동일, model id 만 다름).
PROVIDER_CHIPS: list[dict] = [
    {
        "provider_key": "claude",
        "provider_label": "Claude",
        "models": [
            {
                "key": MODEL_CLAUDE_HAIKU,
                "label": "Haiku 4.5",
                "badge": "빠름·저비용",
            },
            {
                "key": MODEL_CLAUDE_SONNET,
                "label": "Sonnet 4.6",
                "badge": "균형",
            },
            {
                "key": MODEL_CLAUDE_OPUS,
                "label": "Opus 4.7",
                "badge": "1M·깊은 추론",
            },
        ],
    }
]


__all__ = [
    "PROVIDER_CHIPS",
    "stream_chat",
    "create_session",
    "list_sessions",
    "append_message",
    "update_metrics",
]
