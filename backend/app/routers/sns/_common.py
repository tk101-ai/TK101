"""SNS 라우터 패키지 공용 객체 — router/internal_router + 공유 헬퍼.

도메인별 라우터 모듈(`accounts`, `posts`, `stats`, `export`, `collection`,
`comments`, `importers`, `internal`)이 이 모듈의 `router`/`internal_router` 에
엔드포인트를 등록한다. `__init__` 이 같은 객체를 재노출하므로
`from app.routers.sns import router` 가 그대로 동작한다.
"""

import io
import logging
import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse

from app.dependencies import require_internal_token, require_module
from app.modules.constants import Module
from app.services.translation import RateLimitExceeded, check_rate_limit

logger = logging.getLogger("app.routers.sns")

# .xlsx MIME — 내보내기 응답에 쓴다.
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def xlsx_response(buf: io.BytesIO, filename: str) -> StreamingResponse:
    """openpyxl 바이트를 attachment .xlsx 다운로드로 감싼다(UTF-8 파일명)."""
    quoted = urllib.parse.quote(filename)
    return StreamingResponse(
        buf,
        media_type=_XLSX_MIME,
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"},
    )


router = APIRouter(
    prefix="/api/sns",
    tags=["sns"],
    dependencies=[Depends(require_module(Module.MARKETING_SNS.value))],
)

internal_router = APIRouter(
    prefix="/api/internal/sns",
    tags=["sns-internal"],
    dependencies=[Depends(require_internal_token)],
)

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB

# 댓글 분석/번역은 Claude(LLM)를 호출해 비용이 발생한다. 사용자별 슬라이딩 윈도우
# 레이트리밋으로 폭주를 막는다(translator.check_rate_limit 재사용 — 별도 인프라 불필요).
# 일반 호출보다 force(재실행, 캐시 무시)는 더 보수적으로 제한한다.
_LLM_RATE_MAX_CALLS = 20
_LLM_RATE_FORCE_MAX_CALLS = 5
_LLM_RATE_WINDOW_SEC = 60


def enforce_llm_rate_limit(user_id: str, *, force: bool) -> None:
    """댓글 분석/번역 LLM 엔드포인트용 사용자별 레이트리밋.

    force(재실행)는 더 적은 한도를 적용한다. 한도 초과 시 429.
    """
    max_calls = _LLM_RATE_FORCE_MAX_CALLS if force else _LLM_RATE_MAX_CALLS
    try:
        check_rate_limit(
            user_id, max_calls=max_calls, window_sec=_LLM_RATE_WINDOW_SEC
        )
    except RateLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="요청이 너무 잦습니다. 잠시 후 다시 시도하세요.",
        ) from exc
