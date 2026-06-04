from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, Numeric,
    SmallInteger, String, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class EmailImport(Base):
    __tablename__ = "email_imports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email_subject: Mapped[str | None] = mapped_column(String(500))
    email_date: Mapped[date | None] = mapped_column(Date)
    email_sender: Mapped[str | None] = mapped_column(String(200))
    file_name: Mapped[str | None] = mapped_column(String(255))
    # status: 검토중 | 확정 | 무시
    status: Mapped[str] = mapped_column(String(20), default="검토중", nullable=False)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    items: Mapped[list["ImportItem"]] = relationship(
        back_populates="email_import", cascade="all, delete-orphan"
    )


class ImportItem(Base):
    __tablename__ = "import_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    import_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("email_imports.id", ondelete="CASCADE"), nullable=False
    )

    raw_code: Mapped[str | None] = mapped_column(String(50))   # 원본 코드
    raw_name: Mapped[str | None] = mapped_column(String(300))  # 원본 이름

    # 잔고 금액 (NUMERIC 20,2)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 2))
    # 편입 비중 % (NUMERIC 8,4)
    weight_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    # funds.fund_code 와 매칭 (nullable)
    matched_fund_code: Mapped[str | None] = mapped_column(
        String(12), ForeignKey("funds.fund_code", ondelete="SET NULL"), nullable=True
    )
    # 자동 제안 분류 → internal_categories.id (nullable)
    auto_category_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("internal_categories.id", ondelete="SET NULL"), nullable=True
    )

    # match_status: exact | fuzzy | unmatched
    match_status: Mapped[str] = mapped_column(String(20), default="unmatched", nullable=False)

    # 사람이 확정한 분류 → internal_categories.id (nullable)
    confirmed_category_id: Mapped[int | None] = mapped_column(
        SmallInteger, ForeignKey("internal_categories.id", ondelete="SET NULL"), nullable=True
    )
    confirmed_by: Mapped[str | None] = mapped_column(String(100))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # relationships
    email_import: Mapped["EmailImport"] = relationship(back_populates="items")
    matched_fund: Mapped["Fund | None"] = relationship(  # type: ignore[name-defined]
        foreign_keys=[matched_fund_code]
    )
    auto_category: Mapped["InternalCategory | None"] = relationship(  # type: ignore[name-defined]
        foreign_keys=[auto_category_id]
    )
    confirmed_category: Mapped["InternalCategory | None"] = relationship(  # type: ignore[name-defined]
        foreign_keys=[confirmed_category_id]
    )
