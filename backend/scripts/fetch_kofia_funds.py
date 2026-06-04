"""공공데이터포털 금융위원회 펀드상품기본정보 수집 CLI 스크립트.

API 출처: https://www.data.go.kr/data/15094792/openapi.do
엔드포인트: https://apis.data.go.kr/1160100/service/GetFundProductInfoService/getStandardCodeInfo

사용법:
    # 드라이런 (DB 미반영, 통계만 출력)
    python scripts/fetch_kofia_funds.py --dry-run

    # 실제 DB 반영
    python scripts/fetch_kofia_funds.py --api-key YOUR_DATA_GO_KR_KEY

    # .env 의 FSC_API_KEY 사용 (권장)
    python scripts/fetch_kofia_funds.py
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import settings
from app.database import AsyncSessionLocal
from app.services.kofia_sync import sync_fsc_funds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


async def main(api_key: str, dry_run: bool) -> None:
    if not api_key:
        print("오류: API 키가 없습니다.")
        print("  방법 1) --api-key 옵션으로 직접 전달")
        print("  방법 2) .env 에 FSC_API_KEY=키값 추가")
        print("  발급: https://www.data.go.kr → 마이페이지 → 일반 인증키")
        sys.exit(1)

    async with AsyncSessionLocal() as db:
        stats = await sync_fsc_funds(db, api_key=api_key, dry_run=dry_run)

    print("\n── 수집 결과 ──────────────────────────────")
    print(f"  전체 수집:          {stats['total']:,}건")
    print(f"  DB upsert:          {stats['upserted']:,}건")
    print(f"  건너뜀:             {stats['skipped']:,}건")
    print(f"  자동분류 실패:      {stats['no_category']:,}건  ← 수동 분류 필요")
    if dry_run:
        print("  [DRY RUN] DB에 쓰지 않았습니다.")
    print()
    print("  ※ 미제공 필드 (별도 보강 필요):")
    print("     - risk_grade   → 금감원 금융상품한눈에 API (finlife.fss.or.kr)")
    print("     - inception_date → 현재 임시값(1900-01-01) 사용 중")
    print("     - management_company → 펀드명 추출 (정확도 ~80%)")
    print("──────────────────────────────────────────\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key", default=settings.fsc_api_key)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    asyncio.run(main(api_key=args.api_key, dry_run=args.dry_run))
