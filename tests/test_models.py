"""Tests for Arth database models."""

from datetime import date, datetime
from decimal import Decimal

from src.models import Account, Asset, Holding, Metric, Transaction
from src.models.base import AccountType, AssetCategory, TransactionType


class TestAccount:
    """Test Account model."""

    def test_account_creation(self):
        """Test creating an account."""
        account = Account(
            type=AccountType.BANK,
            name="HDFC Bank",
            identifier="HDFC001",
            currency="INR",
            opened_on=date(2020, 1, 1),
        )

        assert account.type == AccountType.BANK
        assert account.name == "HDFC Bank"
        assert account.identifier == "HDFC001"
        assert account.currency == "INR"
        assert account.opened_on == date(2020, 1, 1)

    def test_account_defaults(self):
        """Test account with default values."""
        account = Account(
            type=AccountType.BROKER, name="Zerodha", identifier="ZERODHA001"
        )

        assert account.currency == "INR"
        assert account.opened_on is None


class TestAsset:
    """Test Asset model."""

    def test_asset_creation(self):
        """Test creating an asset."""
        asset = Asset(
            symbol="RELIANCE",
            isin="INE002A01018",
            category=AssetCategory.EQUITY,
            sub_category="Large Cap",
            currency="INR",
        )

        assert asset.symbol == "RELIANCE"
        assert asset.isin == "INE002A01018"
        assert asset.category == AssetCategory.EQUITY
        assert asset.sub_category == "Large Cap"
        assert asset.currency == "INR"

    def test_asset_defaults(self):
        """Test asset with default values."""
        asset = Asset(symbol="INFY", category=AssetCategory.EQUITY)

        assert asset.isin is None
        assert asset.sub_category is None
        assert asset.currency == "INR"


class TestTransaction:
    """Test Transaction model."""

    def test_transaction_creation(self):
        """Test creating a transaction."""
        transaction = Transaction(
            account_id=1,
            asset_id=1,
            posted_at=datetime(2024, 1, 15, 10, 30, 0),
            amount=Decimal("1000.50"),
            currency="INR",
            txn_type=TransactionType.CREDIT,
            raw_source_id="email_123",
        )

        assert transaction.account_id == 1
        assert transaction.asset_id == 1
        assert transaction.amount == Decimal("1000.50")
        assert transaction.txn_type == TransactionType.CREDIT
        assert transaction.raw_source_id == "email_123"

    def test_transaction_defaults(self):
        """Test transaction with default values."""
        transaction = Transaction(
            account_id=1,
            posted_at=datetime.now(),
            amount=Decimal("500.00"),
            txn_type=TransactionType.DEBIT,
        )

        assert transaction.asset_id is None
        assert transaction.currency == "INR"
        assert transaction.raw_source_id is None


class TestHolding:
    """Test Holding model."""

    def test_holding_creation(self):
        """Test creating a holding."""
        holding = Holding(
            asset_id=1,
            qty=Decimal("100.000000"),
            cost_basis=Decimal("1500.00"),
            mkt_value=Decimal("1600.00"),
            as_of=date(2024, 1, 15),
        )

        assert holding.asset_id == 1
        assert holding.qty == Decimal("100.000000")
        assert holding.cost_basis == Decimal("1500.00")
        assert holding.mkt_value == Decimal("1600.00")
        assert holding.as_of == date(2024, 1, 15)


class TestMetric:
    """Test Metric model."""

    def test_metric_creation(self):
        """Test creating a metric."""
        metric = Metric(
            calc_id="net_worth",
            period="day",
            value=Decimal("50000.00"),
            as_of=date(2024, 1, 15),
        )

        assert metric.calc_id == "net_worth"
        assert metric.period == "day"
        assert metric.value == Decimal("50000.00")
        assert metric.as_of == date(2024, 1, 15)


class TestEnums:
    """Test enum values."""

    def test_account_types(self):
        """Test account type enum values."""
        assert AccountType.BANK == "bank"
        assert AccountType.BROKER == "broker"
        assert AccountType.CARD == "card"
        assert AccountType.WALLET == "wallet"

    def test_asset_categories(self):
        """Test asset category enum values."""
        assert AssetCategory.EQUITY == "equity"
        assert AssetCategory.MUTUAL_FUND == "mf"
        assert AssetCategory.BOND == "bond"
        assert AssetCategory.CASH == "cash"
        assert AssetCategory.PROPERTY == "property"

    def test_transaction_types(self):
        """Test transaction type enum values."""
        assert TransactionType.DEBIT == "debit"
        assert TransactionType.CREDIT == "credit"
        assert TransactionType.DIVIDEND == "dividend"
        assert TransactionType.FEE == "fee"
        assert TransactionType.EMI == "emi"
        assert TransactionType.INTEREST == "interest"
