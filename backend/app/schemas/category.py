from pydantic import BaseModel


class CategoryOut(BaseModel):
    id: int
    code: str
    name: str
    level: int
    parent_id: int | None
    is_leaf: bool
    sort_order: int

    model_config = {"from_attributes": True}


class CategoryTreeNode(CategoryOut):
    children: list["CategoryTreeNode"] = []
