"""PlantIt Admin 연동 라우터 — 기관 상품목록 vs admin 등록 상태 비교/적용."""

import re
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.plantit_admin_service import (
    PlantitAdminError,
    SyncItem,
    apply_institution,
    compare_institution,
)

router = APIRouter(prefix="/plantit-sync", tags=["PlantIt Admin 연동"])


class SyncItemIn(BaseModel):
    raw_code: str
    fund_name: str
    product_type: str  # 'fund' | 'etf'


class SyncRequest(BaseModel):
    key: str  # woori | bnk_busan | bnk_gyeongnam
    items: list[SyncItemIn]


class CompareItemOut(BaseModel):
    raw_code: str
    fund_name: str
    product_type: str
    status: str  # asset_missing | universe_missing
    universe_id: Optional[int]


class CompareOut(BaseModel):
    key: str
    universe_note: Optional[str]
    admin_asset_total: int
    universe_counts: dict[int, int]
    registered: int
    missing: list[CompareItemOut]


class ApplyItemOut(BaseModel):
    raw_code: str
    fund_name: str
    ok: bool
    action: str
    detail: str


class ApplyUniverseOut(BaseModel):
    universe_id: int
    universe_name: str
    added: int
    ok: bool
    detail: str


class ApplyOut(BaseModel):
    key: str
    items: list[ApplyItemOut]
    universes: list[ApplyUniverseOut]


# admin 등록 대상은 예탁원 KR 코드(KR7=ETF, KRZ=펀드)만 — 은행 내부 코드(현금성 등) 제외
_KR_CODE_RE = re.compile(r"^KR[A-Z0-9]{10}$")


def _to_sync_items(items: list[SyncItemIn]) -> list[SyncItem]:
    return [
        SyncItem(raw_code=i.raw_code.strip(), fund_name=i.fund_name, product_type=i.product_type)
        for i in items
        if _KR_CODE_RE.match(i.raw_code.strip())
    ]


@router.post("/compare", response_model=CompareOut)
async def compare(body: SyncRequest):
    """이메일 상품 목록과 PlantIt admin 등록 상태 비교 (읽기 전용)."""
    try:
        r = await compare_institution(body.key, _to_sync_items(body.items))
    except PlantitAdminError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return CompareOut(
        key=r.key,
        universe_note=r.universe_note,
        admin_asset_total=r.admin_asset_total,
        universe_counts=r.universe_counts,
        registered=r.registered,
        missing=[
            CompareItemOut(
                raw_code=m.raw_code, fund_name=m.fund_name,
                product_type=m.product_type, status=m.status,
                universe_id=m.universe_id,
            )
            for m in r.missing
        ],
    )


@router.post("/apply", response_model=ApplyOut)
async def apply(body: SyncRequest):
    """미등록 상품을 PlantIt admin에 등록 (자산 신규 + 유니버스 추가)."""
    if not body.items:
        raise HTTPException(status_code=400, detail="적용할 항목이 없습니다")
    try:
        r = await apply_institution(body.key, _to_sync_items(body.items))
    except PlantitAdminError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return ApplyOut(
        key=r.key,
        items=[
            ApplyItemOut(
                raw_code=i.raw_code, fund_name=i.fund_name,
                ok=i.ok, action=i.action, detail=i.detail,
            )
            for i in r.items
        ],
        universes=[
            ApplyUniverseOut(
                universe_id=u.universe_id, universe_name=u.universe_name,
                added=u.added, ok=u.ok, detail=u.detail,
            )
            for u in r.universes
        ],
    )
