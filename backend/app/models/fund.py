from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import (
    BigInteger, Date, DateTime, ForeignKey, Integer, Numeric,
    SmallInteger, String, Text, Boolean, UniqueConstraint, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Fund(Base):
    __tablename__ = "funds"

    fund_code: Mapped[str] = mapped_column(String(12), primary_key=True)
    fund_name: Mapped[str] = mapped_column(String(200), nullable=False)
    fund_name_short: Mapped[str | None] = mapped_column(String(100))

    kofia_fund_type: Mapped[str | None] = mapped_column(String(50))
    internal_category_id: Mapped[int] = mapped_column(SmallInteger, ForeignKey("internal_categories.id"), nullable=False)

    investment_region: Mapped[str] = mapped_column(String(20), default="국내")
    risk_grade: Mapped[int | None] = mapped_column(SmallInteger)

    management_company: Mapped[str] = mapped_column(String(100), nullable=False)
    trustee_company: Mapped[str | None] = mapped_column(String(100))

    inception_date: Mapped[date] = mapped_column(Date, nullable=False)
    maturity_date: Mapped[date | None] = mapped_column(Date)
    base_currency: Mapped[str] = mapped_column(String(3), default="KRW")

    product_type: Mapped[str] = mapped_column(String(10), default="fund")  # fund | etf
    status: Mapped[str] = mapped_column(String(20), default="운용중")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    internal_category: Mapped["InternalCategory"] = relationship(back_populates="funds")  # type: ignore[name-defined]
    nav_history: Mapped[list["FundNav"]] = relationship(back_populates="fund", cascade="all, delete-orphan")
    returns: Mapped[list["FundReturn"]] = relationship(back_populates="fund", cascade="all, delete-orphan")
    fees: Mapped[list["FundFee"]] = relationship(back_populates="fund", cascade="all, delete-orphan")
    risk_metrics: Mapped[list["FundRiskMetric"]] = relationship(back_populates="fund", cascade="all, delete-orphan")


class FundNav(Base):
    __tablename__ = "fund_nav"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(12), ForeignKey("funds.fund_code", ondelete="CASCADE"), nullable=False)
    base_date: Mapped[date] = mapped_column(Date, nullable=False)
    nav: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    aum: Mapped[int | None] = mapped_column(BigInteger)
    units_outstanding: Mapped[int | None] = mapped_column(BigInteger)

    fund: Mapped["Fund"] = relationship(back_populates="nav_history")


class FundReturn(Base):
    __tablename__ = "fund_returns"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(12), ForeignKey("funds.fund_code", ondelete="CASCADE"), nullable=False)
    base_date: Mapped[date] = mapped_column(Date, nullable=False)

    return_1m: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    return_3m: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    return_6m: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    return_ytd: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    return_1y: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    return_3y: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    return_5y: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    return_since_inception: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    annualized_1y: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    annualized_3y: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    annualized_5y: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    fund: Mapped["Fund"] = relationship(back_populates="returns")


class FundFee(Base):
    __tablename__ = "fund_fees"
    __table_args__ = (UniqueConstraint("fund_code", "effective_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fund_code: Mapped[str] = mapped_column(String(12), ForeignKey("funds.fund_code", ondelete="CASCADE"), nullable=False)
    effective_date: Mapped[date] = mapped_column(Date, nullable=False)

    total_expense_ratio: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    management_fee: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    sales_fee: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    trustee_fee: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    admin_fee: Mapped[Decimal | None] = mapped_column(Numeric(6, 4))
    sales_load_front: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    redemption_fee: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=0)
    redemption_fee_period: Mapped[int | None] = mapped_column(SmallInteger)

    fund: Mapped["Fund"] = relationship(back_populates="fees")


class FundRiskMetric(Base):
    __tablename__ = "fund_risk_metrics"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(12), ForeignKey("funds.fund_code", ondelete="CASCADE"), nullable=False)
    base_date: Mapped[date] = mapped_column(Date, nullable=False)
    period: Mapped[str] = mapped_column(String(10), nullable=False)

    std_deviation: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    sharpe_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    information_ratio: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    tracking_error: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    max_drawdown: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    beta: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))
    alpha: Mapped[Decimal | None] = mapped_column(Numeric(8, 4))

    fund: Mapped["Fund"] = relationship(back_populates="risk_metrics")


class DataUpload(Base):
    __tablename__ = "data_uploads"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    data_type: Mapped[str] = mapped_column(String(30), nullable=False)
    base_date: Mapped[date | None] = mapped_column(Date)
    row_count: Mapped[int | None] = mapped_column(Integer)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="처리중")
    error_log: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[str | None] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
