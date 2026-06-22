import secrets
import uuid
from datetime import datetime, timedelta, timezone

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
        sub = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        # sub는 신뢰 불가 입력 — UUID 파싱 실패 시 DB 조회로 넘기지 않고 401(H1, 500 방지).
        try:
            user_id = uuid.UUID(str(sub))
        except (ValueError, AttributeError, TypeError):
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
    # 비번 변경/리셋 후 발급 이전 토큰 무효화(J1): updated_at 이후 발급된 토큰만 유효.
    # 마이그레이션 없이 기존 updated_at(onupdate=now) 컬럼을 재사용한다. 시계 오차/동일
    # 트랜잭션 타이밍으로 인한 오탐 로그아웃을 막기 위해 작은 grace(60초)를 둔다.
    iat = payload.get("iat")
    if iat is not None and user.updated_at is not None:
        token_iat = datetime.fromtimestamp(int(iat), tz=timezone.utc)
        updated = user.updated_at
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        if token_iat < updated - timedelta(seconds=60):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="자격 정보가 변경되어 다시 로그인해야 합니다",
            )
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
