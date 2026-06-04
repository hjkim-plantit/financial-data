from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.fund import Fund
from app.models.category import InternalCategory
from app.schemas.fund import FundCreate, FundUpdate, FundOut, FundListItem

router = APIRouter(prefix="/funds", tags=["펀드"])


class PaginatedFunds(BaseModel):
    items: list[FundListItem]
    total: int
    page: int
    page_size: int


@router.get("/", response_model=PaginatedFunds)
async def list_funds(
    category_id: int | None = Query(None, description="분류 ID (하위 포함 검색)"),
    management_company: str | None = Query(None),
    status: str = Query("운용중", description="운용중 | 판매중단 | 설정취소 | 만기상환 | all"),
    product_type: str = Query("all", description="fund | etf | all"),
    search: str | None = Query(None, description="펀드명 검색"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    skip = (page - 1) * page_size

    status_clause = "1=1" if status == "all" else "f.status = :status"
    ptype_clause = "1=1" if product_type == "all" else "f.product_type = :product_type"
    where = f"""
        WHERE {status_clause}
          AND {ptype_clause}
          AND (:company IS NULL OR f.management_company LIKE '%' || :company || '%')
          AND (:search  IS NULL OR f.fund_name LIKE '%' || :search || '%')
          AND (:cat_id  IS NULL OR c.id = :cat_id OR c.parent_id = :cat_id
               OR (SELECT parent_id FROM internal_categories WHERE id = c.parent_id) = :cat_id)
    """
    params = {
        "status": status,
        "product_type": product_type,
        "company": management_company,
        "search": search,
        "cat_id": category_id,
    }

    count_sql = text(f"""
        SELECT COUNT(*)
        FROM funds f
        JOIN internal_categories c ON f.internal_category_id = c.id
        {where}
    """)
    total = (await db.execute(count_sql, params)).scalar() or 0

    # 최신 기준가·수익률: 상관 서브쿼리로 최신 날짜 조인 (SQLite/PostgreSQL 공용)
    data_sql = text(f"""
        SELECT
            f.fund_code, f.fund_name, f.management_company,
            f.risk_grade, f.status, f.inception_date, f.product_type,
            CASE c.level
                WHEN 1 THEN c.name
                WHEN 2 THEN p1.name || '-' || c.name
                WHEN 3 THEN p2.name || '-' || p1.name || '-' || c.name
            END AS category_full_path
        FROM funds f
        JOIN internal_categories c  ON f.internal_category_id = c.id
        LEFT JOIN internal_categories p1 ON c.parent_id = p1.id
        LEFT JOIN internal_categories p2 ON p1.parent_id = p2.id
        {where}
        ORDER BY f.fund_name
        LIMIT :limit OFFSET :skip
    """)

    rows = (await db.execute(data_sql, {**params, "limit": page_size, "skip": skip})).mappings().all()
    return PaginatedFunds(
        items=[FundListItem(**row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=FundOut, status_code=201)
async def create_fund(body: FundCreate, db: AsyncSession = Depends(get_db)):
    # leaf 분류인지 확인
    cat = await db.get(InternalCategory, body.internal_category_id)
    if not cat:
        raise HTTPException(status_code=400, detail="존재하지 않는 분류입니다")
    if not cat.is_leaf:
        raise HTTPException(status_code=400, detail=f"'{cat.name}'은 중간 분류입니다. leaf 분류를 선택하세요")

    existing = await db.get(Fund, body.fund_code)
    if existing:
        raise HTTPException(status_code=409, detail="이미 등록된 펀드코드입니다")

    fund = Fund(**body.model_dump())
    db.add(fund)
    await db.commit()
    await db.refresh(fund)
    return fund


@router.patch("/{fund_code}", response_model=FundOut)
async def update_fund(fund_code: str, body: FundUpdate, db: AsyncSession = Depends(get_db)):
    fund = await db.get(Fund, fund_code)
    if not fund:
        raise HTTPException(status_code=404, detail="펀드를 찾을 수 없습니다")

    if body.internal_category_id is not None:
        cat = await db.get(InternalCategory, body.internal_category_id)
        if not cat or not cat.is_leaf:
            raise HTTPException(status_code=400, detail="leaf 분류를 선택하세요")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(fund, field, value)

    await db.commit()
    await db.refresh(fund)
    return fund


@router.delete("/{fund_code}", status_code=204)
async def delete_fund(fund_code: str, db: AsyncSession = Depends(get_db)):
    fund = await db.get(Fund, fund_code)
    if not fund:
        raise HTTPException(status_code=404, detail="펀드를 찾을 수 없습니다")
    await db.delete(fund)
    await db.commit()


# ── 미분류 펀드 관리 ──────────────────────────────────────────

class UnclassifiedFundItem(BaseModel):
    fund_code: str
    fund_name: str
    kofia_fund_type: str | None

    class Config:
        from_attributes = True


class BulkCategorizeBody(BaseModel):
    fund_codes: list[str]
    category_id: int


@router.get("/unclassified", response_model=list[UnclassifiedFundItem])
async def list_unclassified_funds(
    search: str | None = Query(None),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    """internal_category_id = 99(미분류) 인 펀드 목록."""
    sql = text("""
        SELECT fund_code, fund_name, kofia_fund_type
        FROM funds
        WHERE internal_category_id = 99
          AND (:search IS NULL OR fund_name LIKE '%' || :search || '%')
        ORDER BY fund_name
        LIMIT :limit OFFSET :skip
    """)
    result = await db.execute(sql, {"search": search, "limit": limit, "skip": skip})
    return [UnclassifiedFundItem(**row) for row in result.mappings().all()]


@router.get("/unclassified/count")
async def count_unclassified_funds(db: AsyncSession = Depends(get_db)):
    result = await db.execute(text("SELECT COUNT(*) FROM funds WHERE internal_category_id = 99"))
    return {"count": result.scalar()}


@router.patch("/bulk-categorize", status_code=200)
async def bulk_categorize(body: BulkCategorizeBody, db: AsyncSession = Depends(get_db)):
    """선택한 펀드들의 internal_category_id 를 일괄 변경."""
    cat = await db.get(InternalCategory, body.category_id)
    if not cat:
        raise HTTPException(status_code=400, detail="존재하지 않는 분류입니다")
    if not cat.is_leaf:
        raise HTTPException(status_code=400, detail=f"'{cat.name}'은 중간 분류입니다. leaf 분류를 선택하세요")
    if not body.fund_codes:
        raise HTTPException(status_code=400, detail="펀드를 선택하세요")

    await db.execute(
        update(Fund)
        .where(Fund.fund_code.in_(body.fund_codes))
        .values(internal_category_id=body.category_id)
    )
    await db.commit()
    return {"updated": len(body.fund_codes), "category_id": body.category_id}


@router.get("/{fund_code}", response_model=FundOut)
async def get_fund(fund_code: str, db: AsyncSession = Depends(get_db)):
    fund = await db.get(Fund, fund_code)
    if not fund:
        raise HTTPException(status_code=404, detail="펀드를 찾을 수 없습니다")
    return fund
