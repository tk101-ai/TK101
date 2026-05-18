"""Telethon SMS 로그인 흐름 — HTTP 두 단계 간 클라이언트 상태 보존.

흐름:
1. ``request_code(persona)`` — Telethon 클라이언트 생성 + ``send_code_request`` 호출
   결과 phone_code_hash 와 client 자체를 메모리에 5분 TTL 로 보관.
2. ``verify_code(persona, code, password?)`` — 보관된 client 로 ``sign_in``.
   성공 시 telegram_user_id / session_path / last_login_at 갱신 후 disconnect.

왜 메모리에 보관하나:
- Telethon ``send_code_request`` 와 ``sign_in`` 은 **동일한 client 인스턴스** 에서
  연속 호출되어야 한다 (phone_code_hash 와 server salt 가 client 에 묶임).
- HTTP 요청 두 번 사이에 동일 인스턴스를 유지하려면 in-process dict 가 가장 단순.
- TTL 5분 — 미완료 로그인은 자동 폐기 + 클라이언트 disconnect.

운영 주의:
- 다중 worker (uvicorn workers >1) 에서는 상태 공유 안 됨 → uvicorn workers=1 유지.
- 외부 Redis 로 옮기려면 client serialize 불가 → 별도 long-lived process 필요.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from telethon import TelegramClient
from telethon.errors import (
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    SessionPasswordNeededError,
)

from app.config import settings
from app.models.distribution import DistributionPersona
from app.services.distribution.encryption import decrypt

logger = logging.getLogger(__name__)

_LOGIN_TTL = timedelta(minutes=5)


@dataclass
class _ActiveLogin:
    """SMS 발송 직후 보관되는 active client 상태."""

    client: TelegramClient
    phone_code_hash: str
    phone: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class LoginExpiredError(RuntimeError):
    """5분 TTL 초과 또는 init 미호출 상태에서 verify 시도."""


class LoginCodeError(RuntimeError):
    """SMS 코드 잘못/만료."""


class LoginPasswordRequired(RuntimeError):
    """2FA 비밀번호 필요. UI 에서 추가 입력 받아 재호출."""


# 모듈 단위 in-memory store. uvicorn workers=1 가정.
_store: dict[UUID, _ActiveLogin] = {}
_store_lock = asyncio.Lock()


async def _cleanup_expired() -> None:
    """TTL 초과한 active login 정리. verify 가 너무 늦으면 client 끊음."""
    now = datetime.now(timezone.utc)
    expired_ids: list[UUID] = []
    async with _store_lock:
        for pid, active in _store.items():
            if now - active.created_at > _LOGIN_TTL:
                expired_ids.append(pid)
        for pid in expired_ids:
            active = _store.pop(pid)
            try:
                await active.client.disconnect()
            except Exception:
                logger.exception("expired login client disconnect 실패")
            logger.info("login TTL 만료 — persona=%s", pid)


def _mask_phone(phone: str) -> str:
    """폰번호 일부만 노출. +82 10 **** 2329 식."""
    if len(phone) < 4:
        return "*" * len(phone)
    return f"{phone[:4]}***{phone[-4:]}"


async def request_code(persona: DistributionPersona) -> dict[str, str]:
    """SMS 인증 코드 발송 트리거.

    Returns:
        ``{"phone_code_hash": "...", "sent_to_phone_masked": "+8210***2329"}``

    Raises:
        ValueError: 자격증명 미설정.
        RuntimeError: Telethon 측 오류.
    """
    if not persona.api_id_enc or not persona.api_hash_enc:
        raise ValueError("자격증명(api_id/api_hash) 미설정. 먼저 등록하세요.")

    await _cleanup_expired()

    session_dir = Path(settings.distribution_telethon_session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)
    # 다른 사용자/프로세스가 .session 파일 읽지 못하도록 디렉토리 권한 강제.
    # Linux 컨테이너 기준 0700. Windows 호스트 마운트는 무시됨 (영향 X).
    try:
        session_dir.chmod(0o700)
    except OSError:
        logger.warning("session dir chmod 0o700 실패 (Windows 가능)")
    session_path = session_dir / f"{persona.account_label}.session"

    api_id = int(decrypt(persona.api_id_enc))
    api_hash = decrypt(persona.api_hash_enc)

    client = TelegramClient(str(session_path), api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        # 이미 인증돼 있음 — verify 단계 건너뛰고 바로 telegram_user_id 갱신은
        # caller 가 verify_code(skip=True) 흐름으로 처리하는 게 깔끔하지만
        # 본 헬퍼는 SMS 발송이 핵심이므로 short-circuit 알림만.
        await client.disconnect()
        raise RuntimeError(
            f"{persona.account_label}: 이미 로그인된 세션이 있습니다. "
            "재로그인이 필요하면 세션 삭제 후 다시 시도하세요."
        )

    try:
        sent = await client.send_code_request(persona.telegram_phone)
    except Exception:
        await client.disconnect()
        raise

    async with _store_lock:
        # 기존 active 있으면 client 정리 후 덮어씀.
        existing = _store.get(persona.id)
        if existing is not None:
            try:
                await existing.client.disconnect()
            except Exception:
                logger.exception("기존 active login disconnect 실패")
        _store[persona.id] = _ActiveLogin(
            client=client,
            phone_code_hash=sent.phone_code_hash,
            phone=persona.telegram_phone,
        )

    logger.info(
        "request_code 완료 — persona=%s phone=%s",
        persona.account_label,
        _mask_phone(persona.telegram_phone),
    )

    return {
        "phone_code_hash": sent.phone_code_hash,
        "sent_to_phone_masked": _mask_phone(persona.telegram_phone),
    }


async def verify_code(
    persona: DistributionPersona,
    db: AsyncSession,
    *,
    code: str,
    password: str | None = None,
) -> dict[str, object]:
    """SMS 코드 + (선택) 2FA 비밀번호 검증, 성공 시 DB 갱신.

    Returns:
        ``{"telegram_user_id": int, "display_name": str, "username": str | None}``

    Raises:
        LoginExpiredError: TTL 만료/active 없음.
        LoginCodeError: SMS 코드 잘못.
        LoginPasswordRequired: 2FA 필요한데 password 미입력.
    """
    await _cleanup_expired()

    async with _store_lock:
        active = _store.get(persona.id)
        if active is None:
            raise LoginExpiredError(
                "active SMS 세션이 없습니다. login-init 부터 다시 진행하세요."
            )

    client = active.client
    # 2FA 비밀번호 대기 케이스에선 client/store 유지 (재시도 가능).
    # 그 외 모든 경로 (성공/SMS 오류/예외) 에서는 cleanup 실행.
    keep_active = False
    try:
        try:
            await client.sign_in(
                phone=active.phone,
                code=code,
                phone_code_hash=active.phone_code_hash,
            )
        except SessionPasswordNeededError:
            if not password:
                # 비밀번호 추가 입력 후 재호출 가능하도록 active 유지.
                keep_active = True
                raise LoginPasswordRequired(
                    "2FA(2단계 인증) 활성. 비밀번호도 함께 제출하세요."
                )
            await client.sign_in(password=password)
        except (PhoneCodeInvalidError, PhoneCodeExpiredError) as exc:
            raise LoginCodeError(f"SMS 코드 오류: {exc}") from exc

        me = await client.get_me()
        if me is None:
            raise RuntimeError("get_me() 결과 None — 알 수 없는 Telethon 상태")

        # DB 갱신.
        session_path = Path(settings.distribution_telethon_session_dir) / f"{persona.account_label}.session"
        # 세션 파일에 0600 권한 강제 — 컨테이너 내 다른 프로세스 읽기 차단.
        try:
            session_path.chmod(0o600)
        except OSError:
            logger.warning("session file chmod 0o600 실패 (Windows 가능)")
        persona.telegram_user_id = me.id
        persona.session_path = str(session_path)
        persona.last_login_at = datetime.now(timezone.utc)
        db.add(persona)
        await db.commit()

        result = {
            "telegram_user_id": me.id,
            "display_name": (getattr(me, "first_name", None) or "") or persona.display_name,
            "username": getattr(me, "username", None),
        }
        logger.info(
            "verify_code 성공 — persona=%s user_id=%s",
            persona.account_label,
            me.id,
        )
        return result
    finally:
        # 2FA 재시도 대기면 cleanup 건너뜀 — 다음 verify-code 호출에서 동일 client 재사용.
        if not keep_active:
            async with _store_lock:
                _store.pop(persona.id, None)
            try:
                await client.disconnect()
            except Exception:
                logger.exception("verify 후 client disconnect 실패")


async def cancel_login(persona_id: UUID) -> bool:
    """사용자가 모달 닫기 등 취소 시 active login 즉시 정리.

    Returns:
        True 면 active 가 있어서 정리됨, False 면 이미 없음.
    """
    async with _store_lock:
        active = _store.pop(persona_id, None)
    if active is None:
        return False
    try:
        await active.client.disconnect()
    except Exception:
        logger.exception("cancel_login disconnect 실패")
    return True
