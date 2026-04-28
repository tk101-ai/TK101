"""마케팅1팀 SNS DB 엑셀 → DB 일괄 적재 CLI.

Usage:
    python -m scripts.migrate_marketing1_excel <xlsx_path>

멱등성 보장: 같은 파일을 여러 번 실행해도 안전.
"""

from __future__ import annotations

import asyncio
import sys

from app.database import async_session
from app.services.sns_importers.marketing1 import import_to_db, parse_workbook


async def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python -m scripts.migrate_marketing1_excel <xlsx_path>")
        sys.exit(2)

    path = sys.argv[1]
    parsed = parse_workbook(path)
    print(
        f"파싱 완료 — accounts={len(parsed['accounts'])}, "
        f"snapshots={len(parsed['snapshots'])}, "
        f"posts={len(parsed['posts'])}"
    )

    async with async_session() as db:
        result = await import_to_db(db, parsed)
        await db.commit()

    print(f"적재 완료 — {result}")


if __name__ == "__main__":
    asyncio.run(main())
