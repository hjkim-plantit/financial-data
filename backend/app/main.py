from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.routers import categories, funds, uploads
from app.routers import imports as imports_router
from app.routers import bank_imports
from app.core.scheduler import setup_scheduler
from app.database import init_db, AsyncSessionLocal
from app.models.category import InternalCategory

_CATEGORY_SEED = [
    {"id": 1,  "code": "equity",           "name": "주식",      "level": 1, "parent_id": None, "is_leaf": True,  "sort_order": 1},
    {"id": 2,  "code": "bond",             "name": "채권",      "level": 1, "parent_id": None, "is_leaf": True,  "sort_order": 2},
    {"id": 3,  "code": "alternative",      "name": "대체투자",  "level": 1, "parent_id": None, "is_leaf": False, "sort_order": 3},
    {"id": 4,  "code": "alt_realestate",   "name": "부동산",    "level": 2, "parent_id": 3,    "is_leaf": True,  "sort_order": 1},
    {"id": 5,  "code": "alt_infra",        "name": "인프라",    "level": 2, "parent_id": 3,    "is_leaf": True,  "sort_order": 2},
    {"id": 6,  "code": "alt_fx",           "name": "통화/외환", "level": 2, "parent_id": 3,    "is_leaf": True,  "sort_order": 3},
    {"id": 7,  "code": "alt_commodity",    "name": "원자재",    "level": 2, "parent_id": 3,    "is_leaf": False, "sort_order": 4},
    {"id": 8,  "code": "commodity_metal",  "name": "금속",      "level": 3, "parent_id": 7,    "is_leaf": True,  "sort_order": 1},
    {"id": 9,  "code": "commodity_energy", "name": "에너지",    "level": 3, "parent_id": 7,    "is_leaf": True,  "sort_order": 2},
    {"id": 10, "code": "commodity_agri",   "name": "농산물",    "level": 3, "parent_id": 7,    "is_leaf": True,  "sort_order": 3},
    {"id": 11, "code": "commodity_other",  "name": "기타",      "level": 3, "parent_id": 7,    "is_leaf": True,  "sort_order": 4},
    {"id": 99, "code": "unclassified",     "name": "미분류",    "level": 1, "parent_id": None, "is_leaf": True,  "sort_order": 99},
]


async def _seed_categories():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(InternalCategory.id))
        existing_ids = set(result.scalars().all())
        added = False
        for data in _CATEGORY_SEED:
            if data["id"] not in existing_ids:
                db.add(InternalCategory(**data))
                added = True
        if added:
            await db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await _seed_categories()
    # DISABLE_SCHEDULER=true 이면 GitHub Actions가 대신 실행
    if os.getenv("DISABLE_SCHEDULER", "false").lower() != "true":
        scheduler = setup_scheduler()
        scheduler.start()
        yield
        scheduler.shutdown(wait=False)
    else:
        yield


app = FastAPI(
    title="국내공모펀드 플랫폼 API",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)

import os
_extra_origins = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173",
                   "http://localhost:5175", *_extra_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(categories.router)
app.include_router(funds.router)
app.include_router(uploads.router)
app.include_router(imports_router.router)
app.include_router(bank_imports.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
