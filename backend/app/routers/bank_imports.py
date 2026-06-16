"""3개 기관 Gmail 첨부파일 뷰어 라우터."""

from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.bank_import_service import fetch_all, save_woori_mapping
from app.services.bank_diff_service import fetch_diff

router = APIRouter(prefix="/bank-imports", tags=["기관 데이터"])


class FundItemOut(BaseModel):
    fund_code: str
    raw_code: str
    fund_name: str
    product_type: str
    available: bool
    risk_grade: Optional[int]
    start_date: Optional[str]
    end_date: Optional[str]
    matched: bool
    asset_class: str
    region: str
    sector: str


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


class FieldChangeOut(BaseModel):
    field: str
    label: str
    old: str
    new: str


class ProductChangeOut(BaseModel):
    fund_code: str
    fund_name: str
    product_type: str
    change_type: str
    changes: list[FieldChangeOut]


class InstitutionDiffOut(BaseModel):
    key: str
    name: str
    today_date: Optional[str]
    yesterday_date: Optional[str]
    added: list[ProductChangeOut]
    removed: list[ProductChangeOut]
    changed: list[ProductChangeOut]
    total_changes: int
    error: Optional[str]


class WooriMappingIn(BaseModel):
    krz_code: str
    k55_code: str


@router.post("/woori/mappings", status_code=200)
async def upsert_woori_mapping(body: WooriMappingIn):
    """우리은행 KRZ→K55 매핑을 CSV에 저장하고 인메모리 캐시를 갱신한다."""
    save_woori_mapping(body.krz_code, body.k55_code)
    return {"krz_code": body.krz_code, "k55_code": body.k55_code}


@router.get("/diff", response_model=list[InstitutionDiffOut])
async def get_diff():
    """전일 vs 당일 첨부파일 비교 — 추가/삭제/변경 상품 반환."""
    data = fetch_diff()
    return [
        InstitutionDiffOut(
            key=r.key, name=r.name,
            today_date=r.today_date, yesterday_date=r.yesterday_date,
            added=[ProductChangeOut(fund_code=i.fund_code, fund_name=i.fund_name, product_type=i.product_type, change_type=i.change_type, changes=[FieldChangeOut(field=f.field, label=f.label, old=f.old, new=f.new) for f in i.changes]) for i in r.added],
            removed=[ProductChangeOut(fund_code=i.fund_code, fund_name=i.fund_name, product_type=i.product_type, change_type=i.change_type, changes=[]) for i in r.removed],
            changed=[ProductChangeOut(fund_code=i.fund_code, fund_name=i.fund_name, product_type=i.product_type, change_type=i.change_type, changes=[FieldChangeOut(field=f.field, label=f.label, old=f.old, new=f.new) for f in i.changes]) for i in r.changed],
            total_changes=r.total_changes,
            error=r.error,
        )
        for r in data
    ]


@router.get("/latest", response_model=list[InstitutionOut])
async def get_latest(db: AsyncSession = Depends(get_db)):
    """3개 기관의 가장 최근 이메일을 파싱해 펀드/ETF로 분리하여 DB와 크로스체크한다."""
    result = await db.execute(
        text("SELECT fund_code, product_type, internal_category_id, investment_region, risk_grade FROM funds")
    )
    rows = result.fetchall()
    db_funds = {r[0] for r in rows if r[1] == "fund"}
    db_etfs  = {r[0] for r in rows if r[1] == "etf"}
    db_meta  = {r[0]: {"category_id": r[2], "region": r[3], "risk_grade": r[4]} for r in rows}

    data = fetch_all(db_funds, db_etfs, db_meta)
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
                    fund_code=i.fund_code, raw_code=i.raw_code,
                    fund_name=i.fund_name,
                    product_type=i.product_type,
                    available=i.available, risk_grade=i.risk_grade,
                    start_date=i.start_date, end_date=i.end_date,
                    matched=i.matched,
                    asset_class=i.asset_class,
                    region=i.region,
                    sector=i.sector,
                )
                for i in r.items
            ],
        )
        for r in data
    ]
