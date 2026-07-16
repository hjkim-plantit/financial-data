"""PlantIt Admin 연동 라우터 — 다기관 상품목록 vs admin 등록 상태 통합 비교/적용."""

import logging
import re
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.plantit_admin_service import (
    UNIVERSE_NAMES,
    PlantitAdminError,
    SyncItem,
    apply_institutions,
    compare_institutions,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/plantit-sync", tags=["PlantIt Admin 연동"])


class SyncItemIn(BaseModel):
    raw_code: str
    fund_name: str
    product_type: str  # 'fund' | 'etf'


class InstitutionItemsIn(BaseModel):
    key: str  # woori | bnk_busan | bnk_gyeongnam
    items: list[SyncItemIn]


class SyncRequest(BaseModel):
    institutions: list[InstitutionItemsIn]


class UniverseTargetOut(BaseModel):
    key: str
    universe_id: int
    universe_name: str


class MissingProductOut(BaseModel):
    raw_code: str
    fund_name: str
    product_type: str
    asset_missing: bool
    universe_targets: list[UniverseTargetOut]
    institutions: list[str]


class InstitutionSummaryOut(BaseModel):
    key: str
    total: int
    registered: int
    missing: int


class CompareOut(BaseModel):
    admin_asset_total: int
    universe_counts: dict[int, int]
    institutions: list[InstitutionSummaryOut]
    universe_note: Optional[str]
    missing: list[MissingProductOut]


class ApplyItemOut(BaseModel):
    raw_code: str
    fund_name: str
    ok: bool
    asset_created: bool
    universes_added: list[int]
    detail: str


class ApplyUniverseOut(BaseModel):
    universe_id: int
    universe_name: str
    added: int
    ok: bool
    detail: str


class ApplyOut(BaseModel):
    items: list[ApplyItemOut]
    universes: list[ApplyUniverseOut]


# admin 등록 대상은 예탁원 KR 코드(KR7=ETF, KRZ=펀드)만 — 은행 내부 코드(현금성 등) 제외
_KR_CODE_RE = re.compile(r"^KR[A-Z0-9]{10}$")


def _to_reqs(body: SyncRequest) -> list[tuple[str, list[SyncItem]]]:
    return [
        (
            inst.key,
            [
                SyncItem(
                    raw_code=i.raw_code.strip(),
                    fund_name=i.fund_name,
                    product_type=i.product_type,
                )
                for i in inst.items
                if _KR_CODE_RE.match(i.raw_code.strip())
            ],
        )
        for inst in body.institutions
    ]


@router.post("/compare", response_model=CompareOut)
async def compare(body: SyncRequest):
    """여러 기관 상품 목록과 PlantIt admin 등록 상태 통합 비교 (읽기 전용)."""
    if not body.institutions:
        raise HTTPException(status_code=400, detail="비교할 기관이 없습니다")
    try:
        r = await compare_institutions(_to_reqs(body))
    except PlantitAdminError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        # 처리 안 된 예외가 CORS 헤더 없는 500으로 나가면 브라우저엔 Network Error로만 보임
        logger.error("plantit-sync compare 실패", exc_info=True)
        raise HTTPException(status_code=500, detail=f"비교 중 오류: {type(e).__name__}: {e}")
    return CompareOut(
        admin_asset_total=r.admin_asset_total,
        universe_counts=r.universe_counts,
        institutions=[
            InstitutionSummaryOut(
                key=s.key, total=s.total, registered=s.registered, missing=s.missing
            )
            for s in r.institutions
        ],
        universe_note=r.universe_note,
        missing=[
            MissingProductOut(
                raw_code=m.raw_code, fund_name=m.fund_name,
                product_type=m.product_type, asset_missing=m.asset_missing,
                universe_targets=[
                    UniverseTargetOut(
                        key=k, universe_id=uid,
                        universe_name=UNIVERSE_NAMES.get(uid, str(uid)),
                    )
                    for k, uid in m.universe_targets
                ],
                institutions=m.institutions,
            )
            for m in r.missing
        ],
    )


@router.post("/apply", response_model=ApplyOut)
async def apply(body: SyncRequest):
    """미등록 상품을 PlantIt admin에 등록 (자산 신규 1회 + 해당 유니버스 전체에 추가)."""
    reqs = _to_reqs(body)
    if not any(items for _, items in reqs):
        raise HTTPException(status_code=400, detail="적용할 항목이 없습니다")
    try:
        r = await apply_institutions(reqs)
    except PlantitAdminError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        logger.error("plantit-sync apply 실패", exc_info=True)
        raise HTTPException(status_code=500, detail=f"적용 중 오류: {type(e).__name__}: {e}")
    return ApplyOut(
        items=[
            ApplyItemOut(
                raw_code=i.raw_code, fund_name=i.fund_name, ok=i.ok,
                asset_created=i.asset_created, universes_added=i.universes_added,
                detail=i.detail,
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
