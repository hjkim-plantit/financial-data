from datetime import date, datetime
from decimal import Decimal
from pydantic import BaseModel, field_validator


# ── Fund ──────────────────────────────────────────────────────
class FundCreate(BaseModel):
    fund_code: str
    fund_name: str
    fund_name_short: str | None = None
    kofia_fund_type: str | None = None
    internal_category_id: int
    investment_region: str = "국내"
    risk_grade: int | None = None
    management_company: str
    trustee_company: str | None = None
    inception_date: date
    maturity_date: date | None = None
    base_currency: str = "KRW"
    status: str = "운용중"

    @field_validator("risk_grade")
    @classmethod
    def validate_risk_grade(cls, v):
        if v is not None and not (1 <= v <= 6):
            raise ValueError("위험등급은 1~6 사이여야 합니다")
        return v


class FundUpdate(BaseModel):
    fund_name: str | None = None
    fund_name_short: str | None = None
    kofia_fund_type: str | None = None
    internal_category_id: int | None = None
    investment_region: str | None = None
    risk_grade: int | None = None
    management_company: str | None = None
    trustee_company: str | None = None
    maturity_date: date | None = None
    status: str | None = None


class FundOut(BaseModel):
    fund_code: str
    fund_name: str
    fund_name_short: str | None
    kofia_fund_type: str | None
    internal_category_id: int
    investment_region: str
    risk_grade: int | None
    management_company: str
    trustee_company: str | None
    inception_date: date
    maturity_date: date | None
    base_currency: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FundListItem(BaseModel):
    """검색 목록용 — 최신 수익률·기준가 포함"""
    fund_code: str
    fund_name: str
    management_company: str
    risk_grade: int | None
    status: str
    inception_date: date | None = None
    product_type: str = "fund"
    category_full_path: str | None = None  # '대체투자-원자재-금속'

    # 최신 기준가
    nav: Decimal | None = None
    aum: int | None = None
    nav_date: date | None = None

    # 최신 수익률
    return_1m: Decimal | None = None
    return_3m: Decimal | None = None
    return_1y: Decimal | None = None

    model_config = {"from_attributes": True}


# ── NAV ──────────────────────────────────────────────────────
class NavCreate(BaseModel):
    fund_code: str
    base_date: date
    nav: Decimal
    aum: int | None = None
    units_outstanding: int | None = None


class NavOut(BaseModel):
    id: int
    fund_code: str
    base_date: date
    nav: Decimal
    aum: int | None
    units_outstanding: int | None

    model_config = {"from_attributes": True}


# ── Returns ──────────────────────────────────────────────────
class ReturnCreate(BaseModel):
    fund_code: str
    base_date: date
    return_1m: Decimal | None = None
    return_3m: Decimal | None = None
    return_6m: Decimal | None = None
    return_ytd: Decimal | None = None
    return_1y: Decimal | None = None
    return_3y: Decimal | None = None
    return_5y: Decimal | None = None
    return_since_inception: Decimal | None = None
    annualized_1y: Decimal | None = None
    annualized_3y: Decimal | None = None
    annualized_5y: Decimal | None = None


# ── Upload ───────────────────────────────────────────────────
class UploadResult(BaseModel):
    upload_id: int
    file_name: str
    data_type: str
    status: str
    row_count: int | None
    error_count: int
    error_log: str | None
