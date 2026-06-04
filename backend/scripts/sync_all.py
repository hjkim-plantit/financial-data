"""전체 데이터 동기화 — 순서대로 실행:
  1. Morningstar 펀드 (판매중단 감지 포함)
  2. fnguide ETF
  3. KOFIA 한글명 업데이트

사용법:
    python scripts/sync_all.py
    python scripts/sync_all.py --dry-run
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
logger = logging.getLogger(__name__)

from sqlalchemy import text
from app.core.config import settings
from app.database import AsyncSessionLocal, init_db
from app.services.morningstar_sync import sync_morningstar_funds
from app.services.etf_sync import sync_etf_funds
from app.services.redash_client import RedashClient
from app.services.kofia_client import FscFundClient


async def main(dry_run: bool) -> None:
    await init_db()
    redash = RedashClient(base_url=settings.redash_url, api_key=settings.redash_api_key)

    # ── Step 1: Morningstar 펀드 ──────────────────────────────
    logger.info("=" * 50)
    logger.info("Step 1/3: Morningstar 펀드 동기화")
    logger.info("=" * 50)
    async with AsyncSessionLocal() as db:
        fund_stats = await sync_morningstar_funds(db, redash, dry_run=dry_run)
    _print_stats("Morningstar 펀드", fund_stats)

    # ── Step 2: fnguide ETF ───────────────────────────────────
    logger.info("=" * 50)
    logger.info("Step 2/3: fnguide ETF 동기화")
    logger.info("=" * 50)
    async with AsyncSessionLocal() as db:
        etf_stats = await sync_etf_funds(db, redash, dry_run=dry_run)
    _print_stats("ETF", etf_stats)

    # ── Step 3: KOFIA 한글명 (펀드만) ────────────────────────
    logger.info("=" * 50)
    logger.info("Step 3/3: KOFIA 한글명 업데이트")
    logger.info("=" * 50)
    if not dry_run:
        async with FscFundClient(api_key=settings.fsc_api_key) as client:
            records = await client.fetch_all_funds()
        kofia_map = {r.aso_std_cd: r.fnd_nm for r in records if r.aso_std_cd and r.fnd_nm}

        async with AsyncSessionLocal() as db:
            result = await db.execute(
                text("SELECT fund_code FROM funds WHERE product_type = 'fund'")
            )
            fund_codes = [row[0] for row in result.fetchall()]
            matched = [(c, kofia_map[c]) for c in fund_codes if c in kofia_map]

            BATCH = 500
            updated = 0
            for i in range(0, len(matched), BATCH):
                batch = matched[i:i + BATCH]
                cases = " ".join(f"WHEN :c{j} THEN :n{j}" for j in range(len(batch)))
                params = {}
                codes_in = []
                for j, (code, name) in enumerate(batch):
                    params[f"c{j}"] = code
                    params[f"n{j}"] = name
                    codes_in.append(f":c{j}")
                await db.execute(
                    text(f"UPDATE funds SET fund_name = CASE fund_code {cases} END WHERE fund_code IN ({', '.join(codes_in)})"),
                    params,
                )
                updated += len(batch)
            await db.commit()

        print(f"\n  KOFIA 한글명: {updated:,}건 업데이트 / 미매칭 {len(fund_codes)-updated:,}건")
    else:
        print("\n  [DRY RUN] KOFIA 한글명 업데이트 건너뜀")

    # ── 최종 요약 ─────────────────────────────────────────────
    print("\n" + "=" * 50)
    print("  최종 DB 현황")
    print("=" * 50)
    if not dry_run:
        async with AsyncSessionLocal() as db:
            r = await db.execute(text("""
                SELECT product_type, status, COUNT(*) as cnt
                FROM funds
                GROUP BY product_type, status
                ORDER BY product_type, status
            """))
            for row in r.fetchall():
                print(f"  {row[0]:6s} | {row[1]:8s} | {row[2]:,}건")
    print()


def _print_stats(label: str, stats: dict) -> None:
    print(f"\n  [{label}] 전체: {stats.get('total',0):,} | "
          f"upsert: {stats.get('upserted',0):,} | "
          f"미분류: {stats.get('no_category',0):,} | "
          f"판매중단: {stats.get('delisted',0):,}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
