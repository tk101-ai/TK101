"""페르소나 단일 필드 안전 갱신 CLI.

용도:
- credentials.json 에서 phone 오기재 등 사후 수정.
- 톤 프로필 / 활성화 토글 / display_name 변경 등.

암호화 필드 (api_id_enc, api_hash_enc) 는 본 도구로 갱신 금지 —
credential_loader 를 다시 돌릴 것.

실행:
    docker compose exec backend python -m app.services.distribution.update_persona \\
        --label KR-A1 --field telegram_phone --value +821049122329
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.distribution import DistributionPersona

logger = logging.getLogger(__name__)

# 본 CLI 로는 절대 변경하면 안 되는 컬럼.
_PROTECTED_FIELDS = {"id", "api_id_enc", "api_hash_enc", "created_at"}
# 갱신 허용 컬럼.
_ALLOWED_FIELDS = {
    "telegram_phone",
    "display_name",
    "active",
    "daily_msg_limit",
    "telegram_user_id",
    "session_path",
    "warmup_until",
}


async def update_field(label: str, field: str, value: str, *, drop_session: bool) -> None:
    if field in _PROTECTED_FIELDS:
        raise ValueError(
            f"필드 {field!r} 는 본 CLI 로 갱신 금지. "
            "암호화 자격증명은 credential_loader 로."
        )
    if field not in _ALLOWED_FIELDS:
        raise ValueError(
            f"필드 {field!r} 는 허용 목록 외. 허용: {sorted(_ALLOWED_FIELDS)}"
        )

    async with async_session() as db:
        q = await db.execute(
            select(DistributionPersona).where(
                DistributionPersona.account_label == label
            )
        )
        persona = q.scalar_one_or_none()
        if persona is None:
            raise ValueError(f"페르소나 {label!r} 없음")

        # 타입 변환.
        cast_value: object
        if field == "active":
            cast_value = value.lower() in {"true", "1", "yes", "y"}
        elif field in ("daily_msg_limit", "telegram_user_id"):
            cast_value = int(value)
        else:
            cast_value = value

        old_value = getattr(persona, field)
        setattr(persona, field, cast_value)
        db.add(persona)
        await db.commit()
        print(f"✅ {label}.{field}: {old_value!r} → {cast_value!r}")

    # phone 갱신 시 기존 Telethon 세션 무효화 옵션.
    if drop_session and field == "telegram_phone":
        session_path = (
            Path(settings.distribution_telethon_session_dir) / f"{label}.session"
        )
        if session_path.exists():
            session_path.unlink()
            print(f"   세션 파일 삭제: {session_path}")
        # journal 파일도 정리.
        journal = session_path.with_suffix(".session-journal")
        if journal.exists():
            journal.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="페르소나 단일 필드 갱신")
    parser.add_argument("--label", required=True, help="account_label (예: KR-A1)")
    parser.add_argument(
        "--field",
        required=True,
        help=f"허용 필드: {sorted(_ALLOWED_FIELDS)}",
    )
    parser.add_argument("--value", required=True, help="새 값")
    parser.add_argument(
        "--drop-session",
        action="store_true",
        help="phone 변경 시 기존 Telethon 세션 파일도 삭제",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    asyncio.run(
        update_field(
            args.label,
            args.field,
            args.value,
            drop_session=args.drop_session,
        )
    )


if __name__ == "__main__":
    main()
