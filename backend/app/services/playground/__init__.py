"""AI Playground 서비스 (T8 Phase 1~3).

구성:
- ``tencent_aigc_client``: 텐센트 MPaaS AIGC OpenAI-compatible SSE 어댑터 (단일 endpoint, model 분기).
- ``token_manager``: VOD CreateAigcApiToken 자동 발급/캐시 (TC3-HMAC-SHA256).
- ``session_manager``: 세션/메시지 DB CRUD.
- ``PROVIDER_CHIPS``: UI 변형 chip 메타 — 8 패밀리 (Claude/OpenAI/Gemini/Grok/GLM/Kimi/MiniMax/DeepSeek).

Provider 라우팅 결정 (T8 PRD 3절 수정):
- 텐센트 AIGC endpoint 1개로 8 공급자를 모두 호출. ``provider_key`` 는 항상 ``tencent_aigc``.
- UI 카드는 "공급자"가 아니라 "모델 패밀리" 단위로 그룹핑 (Claude / GPT / Gemini ...) —
  실제 API 호출 시 carrier 는 동일.
- model 식별자(``key`` 필드)는 텐센트 PPT 표기 기반 추정. 실 호출에서 400/422 반환 시
  사용자 라이브 시험 후 미세 조정.
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
from app.services.playground.token_manager import token_manager

# UI 카드는 "모델 패밀리" 단위로 그룹핑 (텐센트 원본 화면과 동일).
# 실제 API 호출 carrier 는 항상 텐센트 AIGC endpoint 단일.
#
# 2026-05-19 라이브 probe 결과:
# - Claude / Grok: text-aigc OpenAI-compat 에서 모두 400 ("model not available").
#   PPT slide 12 에 따르면 Claude 는 별도 Anthropic SDK wrap 경로 필요. Phase 별도.
# - OpenAI: gpt-5-chat 만 200. 나머지(gpt-5.x, gpt-5-nano, gpt-4o)는 401 — 텐센트
#   콘솔에서 모델 활성화/구매 필요. 활성화 후 추가 노출.
# - MiniMax m2.5 는 401 (m2.7 만 200). 콘솔 활성화 후 추가.
# 2026-06-30 라이브 probe(가이드 doc.tencentpoc.com 기반)로 활성 확인된 모델만 추가.
# ⭐ Claude 는 'cd-' 접두사로 게이트웨이에서 동작(과거 'claude-*' 는 400 → 오인). gpt-5.x
# 는 여전히 400(콘솔 미활성)이라 미추가. 활성화되면 여기 추가.
PROVIDER_CHIPS: list[dict] = [
    {
        "provider_key": "claude",
        "provider_label": "Claude (Anthropic)",
        "models": [
            {"key": "cd-sonnet-4.6", "label": "Claude Sonnet 4.6", "badge": "추천"},
            {"key": "cd-opus-4.8", "label": "Claude Opus 4.8", "badge": "최고"},
            {"key": "cd-haiku-4.5", "label": "Claude Haiku 4.5", "badge": "빠름"},
        ],
    },
    {
        "provider_key": "openai",
        "provider_label": "OpenAI",
        "models": [
            {"key": "gpt-5-chat", "label": "GPT-5 Chat", "badge": None},
            {"key": "gpt-4.1", "label": "GPT-4.1", "badge": None},
            {"key": "gpt-4o", "label": "GPT-4o", "badge": None},
        ],
    },
    {
        "provider_key": "gemini",
        "provider_label": "Gemini",
        "models": [
            {"key": "gemini-3.5-flash", "label": "Gemini 3.5 Flash", "badge": "최신"},
            {"key": "gemini-3.1-flash-lite", "label": "Gemini 3.1 Flash Lite", "badge": "빠름"},
            {"key": "gemini-2.5-pro", "label": "Gemini 2.5 Pro", "badge": None},
            {"key": "gemini-2.5-flash", "label": "Gemini 2.5 Flash", "badge": None},
        ],
    },
    {
        "provider_key": "glm",
        "provider_label": "GLM (Zhipu)",
        "models": [
            {"key": "glm-5.1", "label": "GLM-5.1", "badge": "최신"},
            {"key": "glm-5", "label": "GLM-5", "badge": None},
            {"key": "glm-5-turbo", "label": "GLM-5 Turbo", "badge": "빠름"},
        ],
    },
    {
        "provider_key": "kimi",
        "provider_label": "Kimi (Moonshot)",
        "models": [
            {"key": "kimi-k2.6", "label": "Kimi K2.6", "badge": "최신"},
            {"key": "kimi-k2.5", "label": "Kimi K2.5", "badge": None},
        ],
    },
    {
        "provider_key": "minimax",
        "provider_label": "MiniMax",
        "models": [
            {"key": "minimax-m2.7", "label": "MiniMax M2.7", "badge": "최신"},
            {"key": "minimax-m2.5", "label": "MiniMax M2.5", "badge": None},
        ],
    },
    {
        "provider_key": "deepseek",
        "provider_label": "DeepSeek",
        "models": [
            {"key": "deepseek-v4-pro", "label": "DeepSeek v4 Pro", "badge": "최신"},
            {"key": "deepseek-v4-flash", "label": "DeepSeek v4 Flash", "badge": "빠름"},
            {"key": "deepseek-v3.2", "label": "DeepSeek v3.2", "badge": None},
        ],
    },
    {
        "provider_key": "grok",
        "provider_label": "Grok (xAI)",
        "models": [
            {"key": "gk-4.3", "label": "Grok 4.3", "badge": "신규"},
        ],
    },
]


__all__ = [
    "PROVIDER_CHIPS",
    "stream_chat",
    "create_session",
    "list_sessions",
    "append_message",
    "update_metrics",
    "token_manager",
]
