from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
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

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 24h, matches typical JWT expiry; httpOnly cookie complements the Bearer flow
# so browser navigations (e.g. window.open("/n8n/")) carry credentials too.
ACCESS_COOKIE_NAME = "access_token"
ACCESS_COOKIE_MAX_AGE = 24 * 60 * 60


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """직원 셀프 회원가입. 회사 이메일 도메인만 허용, role=member·status=pending 고정.
    관리자 승인 전까지 로그인 불가(login 의 status 게이트)."""
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
    await db.flush()
    await set_user_departments(db, user.id, [body.department.value])
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if user.status == UserStatus.PENDING.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="승인 대기 중인 계정입니다. 관리자 승인 후 로그인할 수 있습니다",
        )
    if user.status == UserStatus.REJECTED.value:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="가입이 거절된 계정입니다")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
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
