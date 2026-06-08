"""fnguide ts_etf_info + ts_stock → funds 테이블 ETF 동기화.

데이터 소스: Redash data_source_id=23 (TRINO_iceberg_fnguide)
fund_code = isin_cd (KR7... 형식)
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy import delete, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import db_insert
from app.models.fund import Fund, FundFee
from app.services.redash_client import RedashClient

logger = logging.getLogger(__name__)

# ── internal_category_id 매핑 ─────────────────────────────────
# (idx_comm_id_l, idx_comm_id_m) → category_id  (중분류 우선)
_CATEGORY_MAP: dict[tuple[str, str], int] = {
    ("원자재", "금속"):   8,   # commodity_metal
    ("원자재", "에너지"): 9,   # commodity_energy
    ("원자재", "농산물"): 10,  # commodity_agri
    ("통화",   "미국달러"): 6,
    ("통화",   "일본엔"):   6,
    ("통화",   "유로"):     6,
}

# 대분류 fallback
_CATEGORY_L_MAP: dict[str, int] = {
    "주식":    1,
    "채권":    2,
    "부동산":  4,
    "인프라":  5,
    "통화":    6,   # alt_fx
    "원자재":  11,  # commodity_other (중분류 매핑 실패 시)
    "혼합자산": 99,
    "기타":    99,
}

# 자산군 → 위험등급 근사값 (실제 등록 등급이 있으면 덮어씀)
_RISK_GRADE_APPROX: dict[str, int] = {
    "주식":    2,   # 높은위험 (레버리지는 1이지만 구분 불가 → 보수적으로 2)
    "채권":    4,   # 보통위험
    "부동산":  3,   # 다소높은위험
    "인프라":  3,
    "원자재":  2,
    "혼합자산": 3,
}

# ── Redash SQL ────────────────────────────────────────────────

_ETF_SQL = """
SELECT
    s.isin_cd                      AS fund_code,
    s.stk_nm_kor                   AS fund_name,
    e.issue_nm_kor                 AS management_company,
    e.first_settle_dt              AS inception_date,
    e.list_dt,
    e.tot_pay                      AS total_expense_ratio,
    e.tot_pay                      AS management_fee,
    e.idx_comm_id_l                AS asset_class_l,
    e.idx_comm_id_m                AS asset_class_m,
    CASE WHEN s.list_yn = 1 THEN '운용중' ELSE '판매중단' END AS status
FROM iceberg.fnguide.ts_etf_info e
JOIN iceberg.fnguide.ts_stock s ON s.stk_cd = e.etf_cd
WHERE s.isin_cd IS NOT NULL
  AND TRIM(s.isin_cd) <> ''
"""

_REDASH_DS_ID = 23


# ── 동기화 ────────────────────────────────────────────────────

async def sync_etf_funds(
    db: AsyncSession,
    redash: RedashClient,
    dry_run: bool = False,
) -> dict:
    """fnguide ETF 데이터를 funds 테이블에 upsert.

    Returns:
        {"total": N, "upserted": N, "no_category": N}
    """
    logger.info("fnguide ETF 데이터 조회 중...")
    rows = redash.run_query(data_source_id=_REDASH_DS_ID, sql=_ETF_SQL, max_age=0)
    logger.info("ETF 조회 완료: %d건", len(rows))

    stats = {"total": len(rows), "upserted": 0, "no_category": 0}
    today = date.today()

    fund_rows: list[dict] = []
    fee_rows: list[dict] = []

    for row in rows:
        fund_code = _str(row.get("fund_code"))
        if not fund_code:
            continue

        asset_l = _str(row.get("asset_class_l")) or ""
        asset_m = _str(row.get("asset_class_m")) or ""
        category_id = _CATEGORY_MAP.get((asset_l, asset_m), _CATEGORY_L_MAP.get(asset_l, 99))
        if category_id == 99:
            stats["no_category"] += 1

        risk_grade = _RISK_GRADE_APPROX.get(asset_l)

        fund_rows.append({
            "fund_code":            fund_code,
            "fund_name":            _str(row.get("fund_name")) or fund_code,
            "management_company":   _str(row.get("management_company")) or "미상",
            "inception_date":       _parse_date(row.get("inception_date")) or today,
            "risk_grade":           risk_grade,
            "internal_category_id": category_id,
            "product_type":         "etf",
            "status":               _str(row.get("status")) or "운용중",
        })

        ter = _float(row.get("total_expense_ratio"))
        if ter is not None:
            fee_rows.append({
                "fund_code":          fund_code,
                "effective_date":     today,
                "total_expense_ratio": ter,
                "management_fee":     ter,
            })

    if dry_run:
        stats["upserted"] = len(fund_rows)
        logger.info("[DRY RUN] DB 미반영")
        return stats

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
                "internal_category_id": stmt.excluded.internal_category_id,
                "product_type":         stmt.excluded.product_type,
                "status":               stmt.excluded.status,
            },
        )
        await db.execute(stmt)
        logger.info("ETF upsert: %d / %d", min(i + BATCH, len(fund_rows)), len(fund_rows))

    # fund_fees
    await db.execute(
        delete(FundFee).where(
            FundFee.fund_code.in_([r["fund_code"] for r in fee_rows])
        )
    )
    if fee_rows:
        for i in range(0, len(fee_rows), BATCH):
            await db.execute(db_insert(FundFee), fee_rows[i:i + BATCH])

    # risk_grade가 NULL인 ETF에 자산군 근사값 적용 (은행 제공값은 보존)
    approx_rows = [(r["fund_code"], r["risk_grade"]) for r in fund_rows if r["risk_grade"] is not None]
    if approx_rows:
        for i in range(0, len(approx_rows), BATCH):
            batch = approx_rows[i:i + BATCH]
            cases = " ".join(f"WHEN :c{j} THEN :g{j}" for j in range(len(batch)))
            params: dict = {}
            codes_in = []
            for j, (code, grade) in enumerate(batch):
                params[f"c{j}"] = code
                params[f"g{j}"] = grade
                codes_in.append(f":c{j}")
            await db.execute(
                text(f"""
                    UPDATE funds
                    SET risk_grade = CASE fund_code {cases} END
                    WHERE fund_code IN ({", ".join(codes_in)})
                      AND product_type = 'etf'
                      AND risk_grade IS NULL
                """),
                params,
            )

    await db.commit()
    stats["upserted"] = len(fund_rows)
    return stats


# ── 헬퍼 ──────────────────────────────────────────────────────

def _str(val) -> Optional[str]:
    if val is None or val != val:
        return None
    s = str(val).strip()
    return s if s and s.lower() != "nan" else None


def _float(val) -> Optional[float]:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _parse_date(val) -> Optional[date]:
    if not val:
        return None
    s = str(val).strip()
    # YYYYMMDD 형식
    if len(s) == 8 and s.isdigit():
        try:
            return datetime.strptime(s, "%Y%m%d").date()
        except ValueError:
            return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
