"""이메일 임포트 라우터.

엔드포인트:
  POST /imports/trigger          - Gmail에서 오늘 첨부파일 가져와 매칭 처리
  GET  /imports/                 - EmailImport 목록 (최신순)
  GET  /imports/{id}             - 상세 (ImportItem 포함)
  PATCH /imports/{id}/items/{item_id} - confirmed_category_id 업데이트
  POST /imports/{id}/confirm     - 전체 확정 (status → 확정)
"""

import io
from datetime import date, datetime, timezone

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.import_data import EmailImport, ImportItem
from app.schemas.import_data import (
    EmailImportDetail,
    EmailImportOut,
    ImportItemOut,
    ImportItemUpdate,
)
from app.services.gmail_service import fetch_latest_attachment
from app.services.matching_service import match_and_classify

router = APIRouter(prefix="/imports", tags=["이메일 임포트"])


# ---------------------------------------------------------------------------
# POST /imports/trigger
# ---------------------------------------------------------------------------

@router.post("/trigger", response_model=EmailImportOut, status_code=201)
async def trigger_import(db: AsyncSession = Depends(get_db)):
    """Gmail에서 오늘 날짜의 Excel/CSV 첨부파일을 가져와 매칭 처리 후 저장한다."""
    today = date.today()

    try:
        file_name, file_bytes = fetch_latest_attachment(today)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Gmail API 오류: {exc}")

    # 파일 파싱
    try:
        df = _parse_file(file_name, file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"파일 파싱 오류: {exc}")

    # EmailImport 레코드 생성
    email_import = EmailImport(
        email_date=today,
        file_name=file_name,
        status="검토중",
    )
    db.add(email_import)
    await db.flush()  # id 확보

    # 매칭 수행
    matched_items = await match_and_classify(df, db)

    for item_data in matched_items:
        item = ImportItem(
            import_id=email_import.id,
            raw_code=item_data["raw_code"],
            raw_name=item_data["raw_name"],
            amount=item_data["amount"],
            weight_pct=item_data["weight_pct"],
            matched_fund_code=item_data["matched_fund_code"],
            auto_category_id=item_data["auto_category_id"],
            match_status=item_data["match_status"],
        )
        db.add(item)

    await db.commit()
    await db.refresh(email_import)
    return email_import


# ---------------------------------------------------------------------------
# GET /imports/
# ---------------------------------------------------------------------------

@router.get("/", response_model=list[EmailImportOut])
async def list_imports(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
):
    """EmailImport 목록을 최신순으로 반환한다."""
    stmt = (
        select(EmailImport)
        .order_by(EmailImport.imported_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


# ---------------------------------------------------------------------------
# GET /imports/{id}
# ---------------------------------------------------------------------------

@router.get("/{import_id}", response_model=EmailImportDetail)
async def get_import(import_id: int, db: AsyncSession = Depends(get_db)):
    """EmailImport 상세 정보 및 ImportItem 목록을 반환한다."""
    stmt = (
        select(EmailImport)
        .where(EmailImport.id == import_id)
        .options(selectinload(EmailImport.items))
    )
    result = await db.execute(stmt)
    email_import = result.scalar_one_or_none()

    if email_import is None:
        raise HTTPException(status_code=404, detail="임포트 레코드를 찾을 수 없습니다.")

    return email_import


# ---------------------------------------------------------------------------
# PATCH /imports/{id}/items/{item_id}
# ---------------------------------------------------------------------------

@router.patch("/{import_id}/items/{item_id}", response_model=ImportItemOut)
async def update_item(
    import_id: int,
    item_id: int,
    body: ImportItemUpdate,
    db: AsyncSession = Depends(get_db),
):
    """ImportItem 의 confirmed_category_id 를 업데이트한다."""
    stmt = select(ImportItem).where(
        ImportItem.id == item_id,
        ImportItem.import_id == import_id,
    )
    result = await db.execute(stmt)
    item = result.scalar_one_or_none()

    if item is None:
        raise HTTPException(status_code=404, detail="임포트 항목을 찾을 수 없습니다.")

    item.confirmed_category_id = body.confirmed_category_id
    item.confirmed_at = datetime.now(tz=timezone.utc)

    await db.commit()
    await db.refresh(item)
    return item


# ---------------------------------------------------------------------------
# POST /imports/{id}/confirm
# ---------------------------------------------------------------------------

@router.post("/{import_id}/confirm", response_model=EmailImportOut)
async def confirm_import(import_id: int, db: AsyncSession = Depends(get_db)):
    """EmailImport 의 status 를 '확정' 으로 변경한다."""
    stmt = select(EmailImport).where(EmailImport.id == import_id)
    result = await db.execute(stmt)
    email_import = result.scalar_one_or_none()

    if email_import is None:
        raise HTTPException(status_code=404, detail="임포트 레코드를 찾을 수 없습니다.")

    if email_import.status == "확정":
        raise HTTPException(status_code=409, detail="이미 확정된 임포트입니다.")

    email_import.status = "확정"
    await db.commit()
    await db.refresh(email_import)
    return email_import


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _parse_file(file_name: str, file_bytes: bytes) -> pd.DataFrame:
    """파일 이름 확장자에 따라 DataFrame 으로 파싱."""
    buf = io.BytesIO(file_bytes)
    if file_name.lower().endswith(".csv"):
        df = pd.read_csv(buf)
    else:
        df = pd.read_excel(buf)

    # 컬럼명 정규화 (소문자, 앞뒤 공백 제거)
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df
