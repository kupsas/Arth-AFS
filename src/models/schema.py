"""Core database models for Arth."""

from datetime import date, datetime
from decimal import Decimal

from sqlmodel import Field

from .base import AccountType, AssetCategory, BaseModel, TransactionType


class Account(BaseModel, table=True):
    """Account model representing financial accounts."""

    __tablename__ = "accounts"

    type: AccountType = Field(index=True)
    name: str = Field(max_length=255)
    identifier: str = Field(max_length=255, unique=True, index=True)
    currency: str = Field(max_length=3, default="INR")
    opened_on: date | None = Field(default=None)


class Asset(BaseModel, table=True):
    """Asset model representing financial instruments."""

    __tablename__ = "assets"

    symbol: str = Field(max_length=20, index=True)
    isin: str | None = Field(max_length=12, default=None)
    category: AssetCategory = Field(index=True)
    sub_category: str | None = Field(max_length=100, default=None)
    currency: str = Field(max_length=3, default="INR")


class Transaction(BaseModel, table=True):
    """Transaction model representing financial transactions."""

    __tablename__ = "transactions"

    account_id: int = Field(foreign_key="accounts.id", index=True)
    asset_id: int | None = Field(foreign_key="assets.id", default=None)
    posted_at: datetime = Field(index=True)
    amount: Decimal = Field(max_digits=18, decimal_places=2)
    currency: str = Field(max_length=3, default="INR")
    txn_type: TransactionType = Field(index=True)
    raw_source_id: str | None = Field(default=None)


class Holding(BaseModel, table=True):
    """Holding model representing asset positions."""

    __tablename__ = "holdings"

    asset_id: int = Field(foreign_key="assets.id", primary_key=True)
    qty: Decimal = Field(max_digits=18, decimal_places=6)
    cost_basis: Decimal = Field(max_digits=18, decimal_places=2)
    mkt_value: Decimal = Field(max_digits=18, decimal_places=2)
    as_of: date = Field(primary_key=True)


class Metric(BaseModel, table=True):
    """Metric model for precalculated KPIs."""

    __tablename__ = "metrics"

    calc_id: str = Field(max_length=100, index=True)
    period: str = Field(max_length=10)  # day, week, month
    value: Decimal = Field(max_digits=18, decimal_places=2)
    as_of: date = Field(index=True)
