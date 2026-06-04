"""3개 기관 Gmail 첨부파일 뷰어 라우터."""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.bank_import_service import fetch_all

router = APIRouter(prefix="/bank-imports", tags=["기관 데이터"])


class FundItemOut(BaseModel):
    fund_code: str
    fund_name: str
    product_type: str
    available: bool
    risk_grade: Optional[int]
    start_date: Optional[str]
    end_date: Optional[str]
    matched: bool


class InstitutionOut(BaseModel):
    key: str
    name: str
    email_date: Optional[str]
    file_date: Optional[str]
    total: int
    fund_total: int
    fund_matched: int
    etf_total: int
    etf_matched: int
    error: Optional[str]
    items: list[FundItemOut]


@router.get("/latest", response_model=list[InstitutionOut])
async def get_latest(db: AsyncSession = Depends(get_db)):
    """3개 기관의 가장 최근 이메일을 파싱해 펀드/ETF로 분리하여 DB와 크로스체크한다."""
    result = await db.execute(text("SELECT fund_code, product_type FROM funds"))
    rows = result.fetchall()
    db_funds = {r[0] for r in rows if r[1] == "fund"}
    db_etfs  = {r[0] for r in rows if r[1] == "etf"}

    data = fetch_all(db_funds, db_etfs)
    return [
        InstitutionOut(
            key=r.key, name=r.name,
            email_date=r.email_date, file_date=r.file_date,
            total=r.total,
            fund_total=r.fund_total, fund_matched=r.fund_matched,
            etf_total=r.etf_total,  etf_matched=r.etf_matched,
            error=r.error,
            items=[
                FundItemOut(
                    fund_code=i.fund_code, fund_name=i.fund_name,
                    product_type=i.product_type,
                    available=i.available, risk_grade=i.risk_grade,
                    start_date=i.start_date, end_date=i.end_date,
                    matched=i.matched,
                )
                for i in r.items
            ],
        )
        for r in data
    ]
