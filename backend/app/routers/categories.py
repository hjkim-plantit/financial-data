from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.models.category import InternalCategory
from app.schemas.category import CategoryOut, CategoryTreeNode

router = APIRouter(prefix="/categories", tags=["분류"])


@router.get("/", response_model=list[CategoryOut])
async def list_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(InternalCategory).order_by(InternalCategory.level, InternalCategory.sort_order))
    return result.scalars().all()


@router.get("/tree", response_model=list[CategoryTreeNode])
async def category_tree(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(InternalCategory).order_by(InternalCategory.level, InternalCategory.sort_order))
    rows = result.scalars().all()

    nodes = {r.id: CategoryTreeNode.model_validate(r) for r in rows}
    roots = []
    for node in nodes.values():
        if node.parent_id is None:
            roots.append(node)
        else:
            parent = nodes.get(node.parent_id)
            if parent:
                parent.children.append(node)
    return roots


@router.get("/leaves", response_model=list[CategoryOut])
async def leaf_categories(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(InternalCategory)
        .where(InternalCategory.is_leaf == True)
        .order_by(InternalCategory.level, InternalCategory.sort_order)
    )
    return result.scalars().all()
