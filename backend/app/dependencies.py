import secrets

from fastapi import Depends, Header, HTTPException, Request, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.modules.constants import UserRole, UserStatus
from app.modules.registry import user_has_module
from app.services.auth import decode_token


def _extract_token(request: Request) -> str | None:
    """Pull bearer token from Authorization header, falling back to cookie.

    Authorization header takes precedence so existing API clients keep working;
    httpOnly cookie fallback enables browser navigations like window.open("/n8n/")
    where the JS layer cannot attach an Authorization header.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        candidate = auth_header[7:].strip()
        if candidate:
            return candidate
    cookie_token = request.cookies.get("access_token")
    if cookie_token:
        return cookie_token
    return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    token = _extract_token(request)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="인증 필요")
    try:
        payload = decode_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    if user.status != UserStatus.ACTIVE.value:
        # 발급된 토큰의 사후 무효화(관리자 거절/정지 즉시 효력).
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="비활성 계정")
    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="관리자 권한이 필요합니다")
    return user


def require_module(module: str):
    """Dependency factory that gates a route behind a module key.

    Admin role bypasses department check and is granted every module.
    """

    async def checker(user: User = Depends(get_current_user)) -> User:
        if not user_has_module(user, module):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"'{module}' 모듈 접근 권한이 없습니다",
            )
        return user

    checker.__name__ = f"require_module_{module}"
    return checker


async def require_internal_token(x_internal_token: str | None = Header(None, alias="X-Internal-Token")) -> None:
    """System-to-system authentication for n8n / cron callers.

    Compares X-Internal-Token header against settings.internal_api_token using
    constant-time comparison to avoid timing leaks.
    """
    expected = settings.internal_api_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="내부 API 토큰이 설정되지 않았습니다",
        )
    if not x_internal_token or not secrets.compare_digest(x_internal_token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="내부 인증 실패",
        )
