from sqlalchemy import SmallInteger, String, Boolean, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class InternalCategory(Base):
    __tablename__ = "internal_categories"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    level: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(SmallInteger, ForeignKey("internal_categories.id"))
    is_leaf: Mapped[bool] = mapped_column(Boolean, default=False)
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0)

    children: Mapped[list["InternalCategory"]] = relationship(back_populates="parent")
    parent: Mapped["InternalCategory | None"] = relationship(back_populates="children", remote_side=[id])
    funds: Mapped[list["Fund"]] = relationship(back_populates="internal_category")  # type: ignore[name-defined]
