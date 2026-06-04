"""KOFIA API에서 한글 펀드명을 받아 funds.fund_name을 업데이트한다.

Morningstar에서 받은 영문명을 KOFIA 한글명으로 교체.
매핑 기준: funds.fund_code == KOFIA aso_std_cd (12자리 KR 표준코드)

사용법:
    python scripts/update_fund_names_kr.py
    python scripts/update_fund_names_kr.py --dry-run
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
from app.services.kofia_client import FscFundClient


async def main(dry_run: bool) -> None:
    await init_db()

    # 1. KOFIA API에서 전체 한글명 수집
    logger.info("KOFIA API에서 한글 펀드명 수집 중...")
    async with FscFundClient(api_key=settings.fsc_api_key) as client:
        records = await client.fetch_all_funds()

    # aso_std_cd → 한글명 매핑
    kofia_map: dict[str, str] = {
        r.aso_std_cd: r.fnd_nm
        for r in records
        if r.aso_std_cd and r.fnd_nm
    }
    logger.info("KOFIA 수집 완료: %d건", len(kofia_map))

    # 2. 현재 DB의 fund_code 목록 조회
    async with AsyncSessionLocal() as db:
        result = await db.execute(text("SELECT fund_code FROM funds"))
        db_codes = [row[0] for row in result.fetchall()]

    matched = [(code, kofia_map[code]) for code in db_codes if code in kofia_map]
    unmatched = [code for code in db_codes if code not in kofia_map]

    logger.info(
        "매핑 결과 — 매칭: %d건 / 미매칭: %d건 (전체 %d건)",
        len(matched), len(unmatched), len(db_codes),
    )

    if dry_run:
        print("\n[DRY RUN] 샘플 10건:")
        for code, name in matched[:10]:
            print(f"  {code} → {name}")
        return

    # 3. 배치 UPDATE
    BATCH = 500
    updated = 0
    async with AsyncSessionLocal() as db:
        for i in range(0, len(matched), BATCH):
            batch = matched[i:i + BATCH]
            # CASE WHEN 방식으로 한 번에 업데이트
            cases = " ".join(
                f"WHEN :c{j} THEN :n{j}" for j in range(len(batch))
            )
            params = {}
            codes_in = []
            for j, (code, name) in enumerate(batch):
                params[f"c{j}"] = code
                params[f"n{j}"] = name
                codes_in.append(f":c{j}")

            sql = text(f"""
                UPDATE funds
                SET fund_name = CASE fund_code {cases} END
                WHERE fund_code IN ({", ".join(codes_in)})
            """)
            await db.execute(sql, params)
            updated += len(batch)
            logger.info("업데이트: %d / %d", updated, len(matched))

        await db.commit()

    print(f"\n── 업데이트 결과 ─────────────────────")
    print(f"  한글명 업데이트:  {len(matched):,}건")
    print(f"  KOFIA 미매칭:     {len(unmatched):,}건  (영문명 유지)")
    print(f"──────────────────────────────────────\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run))
