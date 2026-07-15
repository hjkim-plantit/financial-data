"""DART 간이투자설명서 → ETF 위험등급 동기화 CLI.

사용법:
    python scripts/fetch_dart_risk_grade.py
    python scripts/fetch_dart_risk_grade.py --limit 20   # 소규모 테스트
    python scripts/fetch_dart_risk_grade.py --only-missing  # 결측치만 재시도
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
from app.services.dart_risk_grade_sync import sync_dart_risk_grades


async def main(limit: int | None, only_missing: bool) -> None:
    await init_db()
    async with AsyncSessionLocal() as db:
        stats = await sync_dart_risk_grades(
            db, dart_api_key=settings.dart_api_key, limit=limit, only_missing=only_missing
        )
    print(
        f"\nDART 위험등급 동기화: 전체 {stats['total']:,} | "
        f"공시매칭 {stats['matched']:,} | 등급반영 {stats['extracted']:,} | "
        f"corp_code없음 {stats['no_corp_code']:,} | 공시못찾음 {stats['no_filing']:,} | "
        f"추출실패 {stats['extract_failed']:,}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--only-missing", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(args.limit, args.only_missing))
