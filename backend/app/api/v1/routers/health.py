"""Health check 엔드포인트.

Design Ref: §4.1 — GET /health (auth 없음, 항상 200 OK)
"""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health", status_code=200)
async def health() -> dict[str, str]:
    """서버 생존 확인.

    향후 확장 가능:
    - DB 연결 확인
    - Redis 연결 확인
    - 외부 의존성(Claude API) 확인
    """
    return {"status": "ok", "service": "tk101-backend", "version": "0.1.0"}
