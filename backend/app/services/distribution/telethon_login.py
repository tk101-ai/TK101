"""Telethon 첫 로그인 CLI — SMS 코드 인터랙티브 입력.

실행:
    docker compose exec -it backend python -m app.services.distribution.telethon_login --label VN-A
    docker compose exec -it backend python -m app.services.distribution.telethon_login --label KR-A1

흐름:
1. account_label 로 페르소나 + 자격증명 조회 + 복호화.
2. Telethon 클라이언트 생성 (.session 파일은 distribution_telethon_data volume 내).
3. 이미 인증돼 있으면 skip — 그냥 telegram_user_id 만 갱신.
4. 미인증이면 send_code_request → 사용자가 SMS 받은 코드 입력 → sign_in.
5. 성공 시 telegram_user_id / session_path / last_login_at 갱신.

주의:
- ``docker compose exec`` 가 아닌 ``docker compose exec -it`` 필수 (stdin 필요).
- 2FA 활성 계정이면 추가 비밀번호 입력. 본 도구는 SMS 만 처리 — 2FA 시 사용자 안내 후 중단.
- 세션 파일이 손상되면 .session 삭제 후 재로그인.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from app.config import settings
from app.database import async_session
from app.models.distribution import DistributionPersona
from app.services.distribution.encryption import decrypt

logger = logging.getLogger(__name__)


async def login_persona(label: str) -> None:
    """단일 페르소나 Telethon 로그인 흐름."""
    session_dir = Path(settings.distribution_telethon_session_dir)
    session_dir.mkdir(parents=True, exist_ok=True)

    async with async_session() as db:
        result = await db.execute(
            select(DistributionPersona).where(
                DistributionPersona.account_label == label
            )
        )
        persona = result.scalar_one_or_none()
        if persona is None:
            raise ValueError(
                f"페르소나 {label} 없음. seeds + credential_loader 먼저 실행."
            )
        if not persona.api_id_enc or not persona.api_hash_enc:
            raise ValueError(
                f"{label} 자격증명 없음. credential_loader 먼저 실행."
            )

        api_id = int(decrypt(persona.api_id_enc))
        api_hash = decrypt(persona.api_hash_enc)
        phone = persona.telegram_phone
        session_path = session_dir / f"{label}.session"

        print(f"\n=== {label} 로그인 시작 ({phone}) ===")
        client = TelegramClient(str(session_path), api_id, api_hash)
        await client.connect()

        try:
            if await client.is_user_authorized():
                print(f"{label}: 이미 로그인됨. telegram_user_id 만 갱신합니다.")
            else:
                # SMS 코드 발송.
                print(f"{label}: SMS 코드 발송 중...")
                sent = await client.send_code_request(phone)
                print(f"폰({phone})으로 SMS 코드 받으셨나요?")
                code = input(f"받은 SMS 코드 입력: ").strip()
                try:
                    await client.sign_in(
                        phone=phone, code=code, phone_code_hash=sent.phone_code_hash
                    )
                except SessionPasswordNeededError:
                    # 2FA 활성. 사용자 안내 + 비밀번호 입력 시도.
                    print(f"{label}: 2FA(2단계 인증) 활성. 비밀번호 필요.")
                    password = input("2FA 비밀번호 입력 (없으면 빈 줄 + Enter, 그러면 중단): ").strip()
                    if not password:
                        await client.disconnect()
                        raise RuntimeError(f"{label}: 2FA 비밀번호 미입력 → 로그인 중단")
                    await client.sign_in(password=password)
                print(f"{label}: SMS 인증 완료.")

            # 본인 정보 조회 + DB 갱신.
            me = await client.get_me()
            persona.telegram_user_id = me.id
            persona.session_path = str(session_path)
            persona.last_login_at = datetime.now(timezone.utc)
            db.add(persona)
            await db.commit()

            print(
                f"{label}: 완료. telegram_user_id={me.id}, "
                f"display_name={getattr(me, 'first_name', '') or ''} "
                f"@{getattr(me, 'username', None) or '(없음)'}"
            )
        finally:
            await client.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Telethon 첫 로그인 (SMS 코드 입력 인터랙티브)"
    )
    parser.add_argument(
        "--label",
        required=True,
        help="페르소나 라벨 (예: VN-A, KR-A1)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    asyncio.run(login_persona(args.label))


if __name__ == "__main__":
    main()
