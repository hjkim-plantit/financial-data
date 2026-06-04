"""Morningstar → funds / fund_fees 동기화 CLI.

사용법:
    # 드라이런 (DB 미반영, 통계만 출력)
    python scripts/fetch_morningstar_funds.py --dry-run

    # 실제 DB 반영
    python scripts/fetch_morningstar_funds.py
"""

import argparse
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
from app.services.morningstar_sync import sync_morningstar_funds
from app.services.redash_client import RedashClient


async def main(dry_run: bool) -> None:
    await init_db()

    redash = RedashClient(
        base_url=settings.redash_url,
        api_key=settings.redash_api_key,
    )

    async with AsyncSessionLocal() as db:
        stats = await sync_morningstar_funds(db, redash, dry_run=dry_run)

    print("\n── 동기화 결과 ──────────────────────────────")
    print(f"  전체 조회:        {stats['total']:,}건")
    print(f"  DB upsert:        {stats['upserted']:,}건")
    print(f"  건너뜀:           {stats['skipped']:,}건")
    print(f"  자동분류 실패:    {stats['no_category']:,}건  ← 수동 분류 필요")
    if dry_run:
        print("  [DRY RUN] DB에 쓰지 않았습니다.")
    print("──────────────────────────────────────────\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    asyncio.run(main(dry_run=args.dry_run))
