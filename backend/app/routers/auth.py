from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.dependencies import get_current_user, require_admin
from app.models.user import User
from app.modules.constants import UserRole, UserStatus
from app.modules.registry import get_user_modules
from app.schemas.auth import (
    LoginRequest,
    PasswordChangeRequest,
    RegisterRequest,
    TokenResponse,
)
from app.schemas.user import UserMe, UserRead
from app.services.auth import create_access_token, hash_password, verify_password
from app.services.department_sync import set_user_departments
from app.services.translation import RateLimitExceeded, check_rate_limit

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 24h, matches typical JWT expiry; httpOnly cookie complements the Bearer flow
# so browser navigations (e.g. window.open("/n8n/")) carry credentials too.
ACCESS_COOKIE_NAME = "access_token"
ACCESS_COOKIE_MAX_AGE = 24 * 60 * 60

# 인증 엔드포인트 레이트리밋(D1) — 무차별 대입/계정 열거/가입 스팸 차단.
# 로그인: 이메일+클라이언트 IP 조합당, 가입: IP당. 인메모리 슬라이딩 윈도우 재사용
# (check_rate_limit, translation 서비스). 한도 초과 시 429.
_LOGIN_MAX_CALLS = 10  # 5분 내 동일 (이메일,IP) 로그인 시도 상한
_LOGIN_WINDOW_SEC = 300
_REGISTER_MAX_CALLS = 5  # 1시간 내 동일 IP 가입 시도 상한
_REGISTER_WINDOW_SEC = 3600


def _client_ip(request: Request) -> str:
    """클라이언트 IP. 리버스 프록시(nginx) 뒤이므로 X-Forwarded-For 첫 홉 우선."""
    fwd = request.headers.get("X-Forwarded-For", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """직원 셀프 회원가입. 회사 이메일 도메인만 허용, role=member·status=pending 고정.
    관리자 승인 전까지 로그인 불가(login 의 status 게이트)."""
    try:
        check_rate_limit(
            f"register:{_client_ip(request)}",
            max_calls=_REGISTER_MAX_CALLS,
            window_sec=_REGISTER_WINDOW_SEC,
        )
    except RateLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="가입 시도가 너무 많습니다. 잠시 후 다시 시도하세요",
        )
    domains = [d.strip().lower() for d in settings.allowed_signup_domains.split(",") if d.strip()]
    email_domain = body.email.split("@")[-1].lower()
    if not domains or email_domain not in domains:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="회사 이메일로만 가입할 수 있습니다",
        )
    existing = (
        await db.execute(select(User).where(User.email == body.email))
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="이미 가입된 이메일입니다")

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        name=body.name,
        department=body.department.value,
        role=UserRole.MEMBER.value,  # 서버 강제(권한상승 방지)
        status=UserStatus.PENDING.value,
        is_active=True,
    )
    db.add(user)
    try:
        await db.flush()
        await set_user_departments(db, user.id, [body.department.value])
        await db.commit()
    except IntegrityError:
        # 사전 존재확인과 commit 사이의 경쟁(동시 동일 이메일 가입) → unique 위반을 409로(F2).
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="이미 가입된 이메일입니다"
        )
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    # (이메일, IP) 조합당 레이트리밋 — 단일 계정 무차별 대입 + 분산 열거 모두 완화(D1).
    try:
        check_rate_limit(
            f"login:{body.email.lower()}:{_client_ip(request)}",
            max_calls=_LOGIN_MAX_CALLS,
            window_sec=_LOGIN_WINDOW_SEC,
        )
    except RateLimitExceeded:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요",
        )
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="이메일 또는 비밀번호가 올바르지 않습니다",
        )
    if user.status == UserStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="승인 대기 중인 계정입니다. 관리자 승인 후 로그인할 수 있습니다",
        )
    if user.status == UserStatus.REJECTED.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="가입이 거절된 계정입니다")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="비활성화된 계정입니다")
    token = create_access_token({"sub": str(user.id)})
    # secure=False because the live host is still plain HTTP; flip to True when HTTPS is added.
    response.set_cookie(
        key=ACCESS_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="strict",
        secure=False,
        max_age=ACCESS_COOKIE_MAX_AGE,
        path="/",
    )
    return TokenResponse(access_token=token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, _user: User = Depends(get_current_user)) -> None:
    """Clear the httpOnly access_token cookie. Front-end still drops its localStorage token."""
    response.delete_cookie(key=ACCESS_COOKIE_NAME, path="/")
    return None


@router.get("/me", response_model=UserMe)
async def me(current_user: User = Depends(get_current_user)):
    return UserMe(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        department=current_user.department,
        role=current_user.role,
        is_active=current_user.is_active,
        status=current_user.status,
        departments=current_user.departments,
        created_at=current_user.created_at,
        modules=get_user_modules(current_user),
    )


@router.patch("/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    body: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """본인 비밀번호 변경.

    - current_password 검증 실패 시 401
    - new_password 길이/공백 검증은 PasswordChangeRequest 에서 422 로 처리
    - 새 비번이 현재와 동일하면 400 (사실상 변경 없음 차단)
    """
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="현재 비밀번호가 일치하지 않습니다",
        )
    if verify_password(body.new_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="새 비밀번호는 현재 비밀번호와 달라야 합니다",
        )
    current_user.hashed_password = hash_password(body.new_password)
    await db.commit()
    return None


@router.get("/admin-check")
async def admin_check(user: User = Depends(require_admin)) -> Response:
    """Lightweight admin gate for nginx auth_request (e.g. /n8n/ reverse proxy).

    Returns 200 + X-User-Email header for admins; require_admin raises 401/403 otherwise.
    """
    return Response(status_code=status.HTTP_200_OK, headers={"X-User-Email": user.email})
