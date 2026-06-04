from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# ImportItem
# ---------------------------------------------------------------------------

class ImportItemOut(BaseModel):
    id: int
    import_id: int
    raw_code: Optional[str] = None
    raw_name: Optional[str] = None
    amount: Optional[Decimal] = None
    weight_pct: Optional[Decimal] = None
    matched_fund_code: Optional[str] = None
    auto_category_id: Optional[int] = None
    match_status: str
    confirmed_category_id: Optional[int] = None
    confirmed_by: Optional[str] = None
    confirmed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ImportItemUpdate(BaseModel):
    """사람이 검토 후 분류를 확정할 때 사용. confirmed_category_id 만 수정 가능."""
    confirmed_category_id: Optional[int] = None


# ---------------------------------------------------------------------------
# EmailImport
# ---------------------------------------------------------------------------

class EmailImportOut(BaseModel):
    id: int
    email_subject: Optional[str] = None
    email_date: Optional[date] = None
    email_sender: Optional[str] = None
    file_name: Optional[str] = None
    status: str
    imported_at: datetime

    model_config = {"from_attributes": True}


class EmailImportDetail(EmailImportOut):
    """상세 조회 시 items 목록 포함."""
    items: list[ImportItemOut] = []
