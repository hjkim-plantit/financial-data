from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False)


def db_insert(model):
    """DB 종류에 따라 dialect-specific insert 반환 (upsert ON CONFLICT 지원)."""
    dialect = engine.dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    else:
        from sqlalchemy.dialects.sqlite import insert
    return insert(model)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


_CATEGORY_SEED = [
    (1,  "equity",          "주식",     1, None, True,  1),
    (2,  "bond",            "채권",     1, None, True,  2),
    (3,  "alternative",     "대체투자", 1, None, False, 3),
    (4,  "alt_realestate",  "부동산",   2, 3,    True,  1),
    (5,  "alt_infra",       "인프라",   2, 3,    True,  2),
    (6,  "alt_fx",          "통화/외환",2, 3,    True,  3),
    (7,  "alt_commodity",   "원자재",   2, 3,    False, 4),
    (8,  "commodity_metal", "금속",     3, 7,    True,  1),
    (9,  "commodity_energy","에너지",   3, 7,    True,  2),
    (10, "commodity_agri",  "농산물",   3, 7,    True,  3),
    (11, "commodity_other", "기타",     3, 7,    True,  4),
    (99, "unclassified",    "미분류",   1, None, True,  99),
]


async def init_db():
    import app.models  # noqa: F401 — ensure all models are registered before create_all
    from sqlalchemy import text
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # 분류 마스터 시드 (없을 때만 삽입)
        count = (await conn.execute(text("SELECT COUNT(*) FROM internal_categories"))).scalar()
        if count == 0:
            await conn.execute(
                text("""
                    INSERT INTO internal_categories
                        (id, code, name, level, parent_id, is_leaf, sort_order)
                    VALUES (:id, :code, :name, :level, :parent_id, :is_leaf, :sort_order)
                """),
                [
                    {"id": r[0], "code": r[1], "name": r[2], "level": r[3],
                     "parent_id": r[4], "is_leaf": r[5], "sort_order": r[6]}
                    for r in _CATEGORY_SEED
                ],
            )
