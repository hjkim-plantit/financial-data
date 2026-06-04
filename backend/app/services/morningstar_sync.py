"""Morningstar 펀드 데이터 → funds / fund_fees 테이블 동기화.

데이터 소스: Redash data_source_id=25 (TRINO_iceberg_morningstar_fund)
테이블: iceberg.morningstar_fund.operation (최신 pit 기준)
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import db_insert
from app.models.fund import Fund, FundFee
from app.services.redash_client import RedashClient

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# 1. Morningstar 분류 → internal_category_id 매핑
# ------------------------------------------------------------------

_ASSET_CLASS_TO_CATEGORY: dict[str, int] = {
    "alt_realestate": 4,
    "alt_infra":      5,
    "alt_metal":      8,
    "alt_energy":     9,
    "alt_other":      11,
    "equity":         1,
    "bond":           2,
    "other":          99,   # 미분류
}

# ------------------------------------------------------------------
# 2. 실행 SQL
# ------------------------------------------------------------------

_MORNINGSTAR_SQL = """
SELECT
    krcode,
    fundname,
    providercompanyname,
    inceptiondate,
    CAST(investmentrisklevelkr AS INTEGER)   AS risk_grade,
    netexpenseratio,
    managementfees_value,
    distributionfees_value,
    administrativefee_value,
    CASE
        WHEN globalcategoryname = 'Real Estate Sector Equity'
            THEN 'alt_realestate'
        WHEN globalcategoryname = 'Infrastructure Sector Equity'
            THEN 'alt_infra'
        WHEN globalcategoryname = 'Precious Metals Sector Equity'
            THEN 'alt_metal'
        WHEN globalcategoryname IN ('Energy Sector Equity', 'Natural Resources Sector Equity')
            THEN 'alt_energy'
        WHEN broadcategorygroup IN ('Commodities', 'Real Assets',
                                    'Alternative', 'Alternative Strategies')
            THEN 'alt_other'
        WHEN broadcategorygroup = 'Equity'
            THEN 'equity'
        WHEN broadcategorygroup IN ('Fixed Income', 'Convertibles', 'Hybrid Securities',
                                    'Money Market', 'Capital Preservation')
            THEN 'bond'
        ELSE 'other'
    END AS asset_class
FROM iceberg.morningstar_fund.operation
WHERE pit = (SELECT MAX(pit) FROM iceberg.morningstar_fund.operation)
  AND krcode IS NOT NULL
  AND TRIM(krcode) <> ''
"""


# ------------------------------------------------------------------
# 3. 동기화 메인 함수
# ------------------------------------------------------------------

async def sync_morningstar_funds(
    db: AsyncSession,
    redash: RedashClient,
    dry_run: bool = False,
) -> dict:
    """Morningstar 최신 데이터를 funds / fund_fees 테이블에 upsert한다.

    Returns:
        {"total": N, "upserted": N, "skipped": N, "no_category": N}
    """
    logger.info("Morningstar 데이터 조회 중...")
    rows = redash.run_query(data_source_id=25, sql=_MORNINGSTAR_SQL, max_age=0)
    logger.info("조회 완료: %d행", len(rows))

    stats = {"total": len(rows), "upserted": 0, "skipped": 0, "no_category": 0}
    today = date.today()

    fund_rows: list[dict] = []
    fee_rows: list[dict] = []

    for row in rows:
        fund_code = _str(row.get("krcode"))
        if not fund_code:
            stats["skipped"] += 1
            continue

        asset_class = row.get("asset_class") or "other"
        category_id = _ASSET_CLASS_TO_CATEGORY.get(asset_class, 99)
        if category_id == 99:
            stats["no_category"] += 1

        inception = _parse_date(row.get("inceptiondate"))

        fund_rows.append({
            "fund_code":            fund_code,
            "fund_name":            _str(row.get("fundname")) or fund_code,
            "management_company":   _str(row.get("providercompanyname")) or "미상",
            "inception_date":       inception or today,
            "risk_grade":           _int(row.get("risk_grade")),
            "internal_category_id": category_id,
            "status":               "운용중",
        })

        # 보수 정보
        if any(row.get(f) is not None for f in (
            "netexpenseratio", "managementfees_value",
            "distributionfees_value", "administrativefee_value"
        )):
            fee_rows.append({
                "fund_code":          fund_code,
                "effective_date":     today,
                "total_expense_ratio": _float(row.get("netexpenseratio")),
                "management_fee":     _float(row.get("managementfees_value")),
                "sales_fee":          _float(row.get("distributionfees_value")),
                "admin_fee":          _float(row.get("administrativefee_value")),
            })

    if dry_run:
        stats["upserted"] = len(fund_rows)
        logger.info("[DRY RUN] DB 미반영")
        return stats

    # funds upsert (배치)
    BATCH = 500
    for i in range(0, len(fund_rows), BATCH):
        batch = fund_rows[i:i + BATCH]
        stmt = db_insert(Fund).values(batch)
        stmt = stmt.on_conflict_do_update(
            index_elements=["fund_code"],
            set_={
                "fund_name":            stmt.excluded.fund_name,
                "management_company":   stmt.excluded.management_company,
                "inception_date":       stmt.excluded.inception_date,
                "risk_grade":           stmt.excluded.risk_grade,
                "internal_category_id": stmt.excluded.internal_category_id,
            },
        )
        await db.execute(stmt)
        logger.info("funds upsert: %d / %d", min(i + BATCH, len(fund_rows)), len(fund_rows))

    # fund_fees: 오늘 날짜 기존 데이터 삭제 후 재삽입 (executemany 방식 — id 자동생성)
    await db.execute(delete(FundFee).where(FundFee.effective_date == today))
    for i in range(0, len(fee_rows), BATCH):
        batch = fee_rows[i:i + BATCH]
        await db.execute(db_insert(FundFee), batch)

    # 이번 배치에 없는 기존 펀드 → 판매중단으로 변경
    active_codes = {r["fund_code"] for r in fund_rows}
    existing = (await db.execute(select(Fund.fund_code))).scalars().all()
    delisted = [c for c in existing if c not in active_codes]
    if delisted:
        await db.execute(
            update(Fund)
            .where(Fund.fund_code.in_(delisted))
            .values(status="판매중단")
        )
        logger.info("판매중단 처리: %d건", len(delisted))
        stats["delisted"] = len(delisted)

    await db.commit()
    stats["upserted"] = len(fund_rows)
    return stats


# ------------------------------------------------------------------
# 헬퍼
# ------------------------------------------------------------------

def _str(val) -> Optional[str]:
    if val is None or val != val:  # nan check
        return None
    s = str(val).strip()
    return s if s and s.lower() != "nan" else None


def _int(val) -> Optional[int]:
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f  # nan → None
    except (TypeError, ValueError):
        return None


def _parse_date(val) -> Optional[date]:
    if not val:
        return None
    if isinstance(val, date):
        return val
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
