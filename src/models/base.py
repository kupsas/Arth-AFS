"""Base models and enums for Arth database schema."""

from datetime import datetime
from enum import Enum

from sqlmodel import Field, SQLModel


class AccountType(str, Enum):
    """Account types supported by Arth."""

    BANK = "bank"
    BROKER = "broker"
    CARD = "card"
    WALLET = "wallet"


class AssetCategory(str, Enum):
    """Asset categories for classification."""

    EQUITY = "equity"
    MUTUAL_FUND = "mf"
    BOND = "bond"
    CASH = "cash"
    PROPERTY = "property"


class TransactionType(str, Enum):
    """Transaction types for classification."""

    DEBIT = "debit"
    CREDIT = "credit"
    DIVIDEND = "dividend"
    FEE = "fee"
    EMI = "emi"
    INTEREST = "interest"


class BaseModel(SQLModel):
    """Base model with common fields."""

    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
