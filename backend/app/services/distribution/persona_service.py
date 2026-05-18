"""페르소나 CRUD 서비스 — DB 작업 + 자격증명 암호화 책임.

규칙:
- 평문 api_id/api_hash 는 절대 DB 컬럼에 직접 저장 X. 반드시 ``encrypt`` 통과.
- ``to_out`` 은 평문 자격증명을 반환 X — ``has_credentials`` 불리언으로만 노출.
- ``session_path`` 존재 여부로 로그인 완료 판단 (``is_logged_in``).
"""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.distribution import DistributionPersona
from app.schemas.distribution import PersonaCreate, PersonaOut, PersonaUpdate
from app.services.distribution.encryption import encrypt

logger = logging.getLogger(__name__)


def to_out(persona: DistributionPersona) -> PersonaOut:
    """ORM → API 응답 변환. 평문 자격증명 절대 노출 X."""
    has_creds = bool(persona.api_id_enc and persona.api_hash_enc)
    is_logged_in = bool(persona.session_path) and bool(persona.telegram_user_id)
    return PersonaOut(
        id=persona.id,
        account_label=persona.account_label,
        role=persona.role,  # type: ignore[arg-type]  # Literal 비교는 Pydantic 이 검증
        display_name=persona.display_name,
        telegram_phone=persona.telegram_phone,
        telegram_user_id=persona.telegram_user_id,
        has_credentials=has_creds,
        is_logged_in=is_logged_in,
        tone_profile=persona.tone_profile,
        daily_msg_limit=persona.daily_msg_limit,
        active=persona.active,
        warmup_until=persona.warmup_until,
        last_login_at=persona.last_login_at,
        created_at=persona.created_at,
        updated_at=persona.updated_at,
    )


async def list_personas(db: AsyncSession) -> list[DistributionPersona]:
    result = await db.execute(
        select(DistributionPersona).order_by(DistributionPersona.account_label)
    )
    return list(result.scalars())


async def get_persona(
    db: AsyncSession, persona_id: UUID
) -> DistributionPersona | None:
    result = await db.execute(
        select(DistributionPersona).where(DistributionPersona.id == persona_id)
    )
    return result.scalar_one_or_none()


async def get_persona_by_label(
    db: AsyncSession, label: str
) -> DistributionPersona | None:
    result = await db.execute(
        select(DistributionPersona).where(DistributionPersona.account_label == label)
    )
    return result.scalar_one_or_none()


async def create_persona(
    db: AsyncSession, data: PersonaCreate
) -> DistributionPersona:
    """새 페르소나 등록. api_id/api_hash 는 받는 즉시 Fernet 암호화 후 저장.

    중복 라벨이면 IntegrityError 발생 → 라우터가 409 로 변환.
    """
    persona = DistributionPersona(
        account_label=data.account_label,
        role=data.role,
        display_name=data.display_name,
        telegram_phone=data.telegram_phone,
        api_id_enc=encrypt(data.api_id),
        api_hash_enc=encrypt(data.api_hash),
        tone_profile=data.tone_profile,
        daily_msg_limit=data.daily_msg_limit,
    )
    # warmup_until 자동 설정 (등록일 + warmup_days).
    if data.warmup_days > 0:
        from datetime import date, timedelta

        persona.warmup_until = date.today() + timedelta(days=data.warmup_days)

    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    logger.info(
        "persona created — label=%s role=%s phone=%s",
        persona.account_label,
        persona.role,
        persona.telegram_phone,
    )
    return persona


async def update_persona(
    db: AsyncSession, persona_id: UUID, data: PersonaUpdate
) -> DistributionPersona | None:
    persona = await get_persona(db, persona_id)
    if persona is None:
        return None
    updates = data.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(persona, k, v)
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return persona


async def delete_persona(
    db: AsyncSession, persona_id: UUID, *, drop_session_file: bool = True
) -> bool:
    """페르소나 hard delete. 송신 이력은 ON DELETE RESTRICT 로 보호됨.

    drop_session_file: True 면 디스크의 .session 파일도 같이 삭제.
    """
    persona = await get_persona(db, persona_id)
    if persona is None:
        return False
    session_path = persona.session_path
    await db.delete(persona)
    await db.commit()

    if drop_session_file and session_path:
        p = Path(session_path)
        try:
            if p.exists():
                p.unlink()
            journal = p.with_suffix(".session-journal")
            if journal.exists():
                journal.unlink()
        except OSError:
            logger.exception("session file 삭제 실패 — 수동 정리 필요: %s", p)
    return True


async def logout_persona(
    db: AsyncSession, persona_id: UUID
) -> DistributionPersona | None:
    """세션 파일 삭제 + DB 플래그 클리어. 자격증명은 보존."""
    persona = await get_persona(db, persona_id)
    if persona is None:
        return None
    if persona.session_path:
        p = Path(persona.session_path)
        try:
            if p.exists():
                p.unlink()
            journal = p.with_suffix(".session-journal")
            if journal.exists():
                journal.unlink()
        except OSError:
            logger.exception("logout 시 session 파일 삭제 실패: %s", p)
    persona.session_path = None
    persona.telegram_user_id = None
    persona.last_login_at = None
    db.add(persona)
    await db.commit()
    await db.refresh(persona)
    return persona
