from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt

from app.config import settings

# bcrypt는 입력 비밀번호를 72바이트까지만 사용하고 초과분은 조용히 버린다.
# 일부 bcrypt 빌드는 72바이트 초과 입력에 ValueError를 던지므로, 해시/검증 양쪽에서
# 동일하게 72바이트로 절단해 일관성을 보장한다(H3). UTF-8 멀티바이트가 경계에서
# 잘려도 hash/verify가 같은 바이트열을 쓰므로 검증은 정상 동작한다.
_BCRYPT_MAX_BYTES = 72


def _bcrypt_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_bytes(password), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(_bcrypt_bytes(password), hashed.encode())


def create_access_token(data: dict) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.access_token_expire_minutes)
    # iat: 비번 변경 후 기존 토큰 무효화(J1)를 위해 발급 시각을 기록.
    to_encode = {**data, "iat": now, "exp": expire}
    return jwt.encode(to_encode, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    # require: exp/sub 누락 토큰을 거부(J3). exp 누락 토큰의 무기한 사용 차단.
    return jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        options={"require": ["exp", "sub"]},
    )
