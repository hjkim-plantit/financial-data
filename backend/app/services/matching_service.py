"""펀드 코드 매칭 및 분류 자동 제안 서비스.

데이터프레임의 fund_code 컬럼을 DB의 funds 테이블과 exact 매칭하고,
매칭된 펀드의 internal_category_id 를 auto_category_id 로 제안한다.
"""

from __future__ import annotations

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fund import Fund


async def match_and_classify(
    df: pd.DataFrame,
    db: AsyncSession,
) -> list[dict]:
    """데이터프레임의 각 행을 funds 테이블과 매칭하여 결과 dict 목록을 반환.

    Args:
        df: 최소한 'fund_code' 컬럼을 포함하는 DataFrame.
            선택 컬럼: fund_name (원본 이름), amount (잔고), weight_pct (편입 비중).
        db: 비동기 DB 세션.

    Returns:
        각 행에 대한 매칭 결과 dict 목록.
        키: raw_code, raw_name, amount, weight_pct,
             matched_fund_code, auto_category_id, match_status
    """
    if df.empty:
        return []

    # DataFrame 에서 fund_code 목록 추출 (중복 제거)
    raw_codes: list[str] = df["fund_code"].dropna().unique().tolist()

    # DB에서 해당 코드들을 한 번에 조회
    stmt = select(Fund.fund_code, Fund.internal_category_id).where(
        Fund.fund_code.in_(raw_codes)
    )
    result = await db.execute(stmt)
    rows = result.fetchall()

    # fund_code → internal_category_id 매핑 딕셔너리
    code_to_category: dict[str, int] = {
        row.fund_code: row.internal_category_id for row in rows
    }

    results: list[dict] = []
    for _, row in df.iterrows():
        raw_code: str | None = _to_str(row.get("fund_code"))
        raw_name: str | None = _to_str(row.get("fund_name") or row.get("fund_name_short"))
        amount = _to_decimal_or_none(row.get("amount"))
        weight_pct = _to_decimal_or_none(row.get("weight_pct"))

        if raw_code and raw_code in code_to_category:
            matched_fund_code = raw_code
            auto_category_id: int | None = code_to_category[raw_code]
            match_status = "exact"
        else:
            matched_fund_code = None
            auto_category_id = None
            match_status = "unmatched"

        results.append(
            {
                "raw_code": raw_code,
                "raw_name": raw_name,
                "amount": amount,
                "weight_pct": weight_pct,
                "matched_fund_code": matched_fund_code,
                "auto_category_id": auto_category_id,
                "match_status": match_status,
            }
        )

    return results


# ---------------------------------------------------------------------------
# 헬퍼 함수
# ---------------------------------------------------------------------------

def _to_str(value) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return str(value).strip() or None


def _to_decimal_or_none(value):
    """숫자 값을 float 또는 None 으로 변환 (SQLAlchemy Numeric 호환)."""
    if value is None:
        return None
    try:
        if isinstance(value, float) and pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
