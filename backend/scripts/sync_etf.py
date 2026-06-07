"""ETF 동기화 CLI."""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

from app.core.config import settings
from app.database import AsyncSessionLocal, init_db
from app.services.etf_sync import sync_etf_funds
from app.services.redash_client import RedashClient


async def main() -> None:
    await init_db()
    redash = RedashClient(base_url=settings.redash_url, api_key=settings.redash_api_key)
    async with AsyncSessionLocal() as db:
        stats = await sync_etf_funds(db, redash)
    print(f"ETF 동기화: 전체 {stats.get('total',0):,} | upsert {stats.get('upserted',0):,}")


if __name__ == "__main__":
    asyncio.run(main())
