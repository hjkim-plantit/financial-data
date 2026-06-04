import io
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd
from app.database import get_db
from app.models.fund import FundNav, FundReturn, FundFee, DataUpload
from app.schemas.fund import UploadResult

router = APIRouter(prefix="/uploads", tags=["업로드"])

COLUMN_MAP = {
    "nav": {
        "required": ["fund_code", "base_date", "nav"],
        "optional": ["aum", "units_outstanding"],
    },
    "returns": {
        "required": ["fund_code", "base_date"],
        "optional": ["return_1m","return_3m","return_6m","return_ytd",
                     "return_1y","return_3y","return_5y","return_since_inception",
                     "annualized_1y","annualized_3y","annualized_5y"],
    },
    "fees": {
        "required": ["fund_code", "effective_date"],
        "optional": ["total_expense_ratio","management_fee","sales_fee",
                     "trustee_fee","admin_fee","sales_load_front",
                     "redemption_fee","redemption_fee_period"],
    },
}

MODEL_MAP = {
    "nav": FundNav,
    "returns": FundReturn,
    "fees": FundFee,
}


def _read_file(file: UploadFile) -> pd.DataFrame:
    content = file.file.read()
    if file.filename.endswith(".csv"):
        return pd.read_csv(io.BytesIO(content))
    return pd.read_excel(io.BytesIO(content))


@router.post("/{data_type}", response_model=UploadResult)
async def upload_file(
    data_type: str,
    base_date: date | None = Form(None),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if data_type not in COLUMN_MAP:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 타입: {data_type}. 가능한 값: {list(COLUMN_MAP)}")

    upload = DataUpload(
        file_name=file.filename,
        data_type=data_type,
        base_date=base_date,
        status="처리중",
    )
    db.add(upload)
    await db.flush()

    try:
        df = _read_file(file)
        df.columns = [c.strip().lower() for c in df.columns]

        spec = COLUMN_MAP[data_type]
        missing = [c for c in spec["required"] if c not in df.columns]
        if missing:
            raise ValueError(f"필수 컬럼 없음: {missing}")

        Model = MODEL_MAP[data_type]
        rows, errors = [], []

        for i, row in df.iterrows():
            try:
                data = {c: (None if pd.isna(row[c]) else row[c])
                        for c in spec["required"] + spec["optional"] if c in df.columns}
                rows.append(Model(**data))
            except Exception as e:
                errors.append(f"행 {i+2}: {e}")

        if rows:
            db.add_all(rows)

        upload.row_count = len(rows)
        upload.error_count = len(errors)
        upload.error_log = "\n".join(errors) if errors else None
        upload.status = "완료" if not errors else ("완료" if rows else "오류")
        await db.commit()

    except Exception as e:
        upload.status = "오류"
        upload.error_log = str(e)
        await db.commit()
        raise HTTPException(status_code=422, detail=str(e))

    return UploadResult(
        upload_id=upload.id,
        file_name=upload.file_name,
        data_type=upload.data_type,
        status=upload.status,
        row_count=upload.row_count,
        error_count=upload.error_count,
        error_log=upload.error_log,
    )
