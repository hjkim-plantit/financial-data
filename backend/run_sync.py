"""KOFIA 펀드 sync 1회 실행 스크립트."""
import asyncio
import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

from app.database import AsyncSessionLocal, init_db
from app.services.kofia_sync import sync_fsc_funds
from app.core.config import settings


async def main():
    await init_db()
    async with AsyncSessionLocal() as db:
        result = await sync_fsc_funds(db, api_key=settings.fsc_api_key, dry_run=False)
    print("완료:", result)

asyncio.run(main())
