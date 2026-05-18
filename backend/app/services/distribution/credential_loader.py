"""자격증명 JSON → Fernet 암호화 → DB 저장 → 평문 파일 삭제.

실행:
    docker compose exec backend python -m app.services.distribution.credential_loader

입력 파일 (호스트의 ``./.local/t9_credentials.json`` → 컨테이너 ``/srv/.local/t9_credentials.json``):
{
  "VN-A": {
    "phone": "+84xxxxxxxxx",
    "api_id": "12345678",
    "api_hash": "abc..."
  },
  "KR-A1": { ... }
}

처리:
1. JSON 파싱.
2. account_label 로 DistributionPersona 조회 (시드되어 있어야 함).
3. phone / api_id (encrypt) / api_hash (encrypt) 저장.
4. 성공 후 **평문 JSON 파일 즉시 삭제** (보안 정책).

실패 시:
- 평문 파일 그대로 유지 → 디버깅 후 재시도.
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from sqlalchemy import select

from app.database import async_session
from app.models.distribution import DistributionPersona
from app.services.distribution.encryption import EncryptionError, encrypt

logger = logging.getLogger(__name__)

# 컨테이너 내부 경로 (docker-compose 가 호스트 ./.local 을 /srv/.local 로 mount).
CREDENTIAL_PATH = Path("/srv/.local/t9_credentials.json")


async def load_credentials() -> int:
    """JSON 파일을 읽어 페르소나에 자격증명을 채워넣고, 성공 시 평문 파일 삭제.

    Returns:
        성공적으로 갱신된 페르소나 수.
    """
    if not CREDENTIAL_PATH.exists():
        raise FileNotFoundError(
            f"{CREDENTIAL_PATH} 가 없습니다. "
            "호스트의 ./.local/t9_credentials.json 에 자격증명 JSON 을 배치하세요."
        )

    raw = CREDENTIAL_PATH.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"자격증명 JSON 파싱 실패: {exc}") from exc

    if not isinstance(data, dict) or not data:
        raise ValueError("자격증명 JSON 은 비어있지 않은 객체여야 합니다.")

    updated = 0
    async with async_session() as session:
        for label, creds in data.items():
            if not isinstance(creds, dict):
                logger.warning("스킵 — %s 항목이 객체가 아님", label)
                continue
            phone = creds.get("phone")
            api_id = creds.get("api_id")
            api_hash = creds.get("api_hash")
            if not (phone and api_id and api_hash):
                logger.warning(
                    "스킵 — %s: phone/api_id/api_hash 중 누락",
                    label,
                )
                continue

            result = await session.execute(
                select(DistributionPersona).where(
                    DistributionPersona.account_label == label
                )
            )
            persona = result.scalar_one_or_none()
            if persona is None:
                logger.warning(
                    "스킵 — %s 페르소나가 DB 에 없음. 먼저 seeds 실행 필요.",
                    label,
                )
                continue

            try:
                persona.telegram_phone = str(phone)
                persona.api_id_enc = encrypt(str(api_id))
                persona.api_hash_enc = encrypt(str(api_hash))
                session.add(persona)
            except EncryptionError as exc:
                # DISTRIBUTION_FERNET_KEY 미설정 등 — 전체 중단.
                raise RuntimeError(
                    f"암호화 실패 — {exc}. .env 의 DISTRIBUTION_FERNET_KEY 확인."
                ) from exc

            updated += 1
            logger.info("%s 자격증명 갱신 완료 (phone=%s)", label, phone)

        if updated:
            await session.commit()

    # 처리 결과와 무관하게 평문 파일 삭제 — 부분 실패한 항목도 평문이 디스크에 남으면 안 됨.
    # 실패한 항목이 있으면 위 logger.warning 으로 어느 라벨인지 표시되므로,
    # 사용자가 그 라벨만 다시 작성해서 새 파일 만들 수 있음.
    try:
        CREDENTIAL_PATH.unlink()
        logger.info("평문 자격증명 파일 삭제 완료 (처리 결과 무관): %s", CREDENTIAL_PATH)
    except OSError as exc:
        logger.error(
            "평문 파일 삭제 실패! 즉시 수동 삭제 필요: %s (원인: %s)",
            CREDENTIAL_PATH,
            exc,
        )

    return updated


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    count = asyncio.run(load_credentials())
    print(f"\n총 {count} 개 페르소나 자격증명 갱신 완료.")
    if count > 0:
        print("다음: docker compose exec backend python -m app.services.distribution.telethon_login --label VN-A")


if __name__ == "__main__":
    main()
