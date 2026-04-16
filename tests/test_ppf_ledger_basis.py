"""PPF deployed capital from linked ledger (contributions, excluding interest)."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from api.models import Holding, InvestmentTransaction
from api.services.holdings_metrics import holding_cost_basis
from api.services.ppf_ledger_basis import ppf_net_contributions_from_ledger
from pipeline.models import AssetClass, InvestmentTxnType, ValuationMethod


@pytest.fixture(name="engine")
def _engine():
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture(name="session")
def _session(engine):
    with Session(engine) as s:
        yield s


def test_ppf_net_contributions_excludes_dividend(session: Session) -> None:
    h = Holding(
        name="PPF",
        asset_class=AssetClass.PPF.value,
        account_platform="ICICI PPF",
        valuation_method=ValuationMethod.FIXED_RETURN.value,
        liquidity_class="ILLIQUID",
        user_id="sashank",
        principal_amount=1500.0,
        current_value=701_830.0,
    )
    session.add(h)
    session.commit()
    session.refresh(h)
    hid = h.id
    assert hid is not None

    session.add_all(
        [
            InvestmentTransaction(
                txn_date=datetime.date(2020, 4, 5),
                symbol=None,
                txn_type=InvestmentTxnType.BUY.value,
                quantity=1.0,
                price_per_unit=500_000.0,
                total_amount=500_000.0,
                account_platform="ICICI PPF",
                holding_id=hid,
            ),
            InvestmentTransaction(
                txn_date=datetime.date(2021, 4, 5),
                symbol=None,
                txn_type=InvestmentTxnType.BUY.value,
                quantity=1.0,
                price_per_unit=77_500.0,
                total_amount=77_500.0,
                account_platform="ICICI PPF",
                holding_id=hid,
            ),
            InvestmentTransaction(
                txn_date=datetime.date(2022, 3, 31),
                symbol=None,
                txn_type=InvestmentTxnType.DIVIDEND.value,
                quantity=1.0,
                price_per_unit=124_330.0,
                total_amount=124_330.0,
                account_platform="ICICI PPF",
                holding_id=hid,
            ),
        ]
    )
    session.commit()

    assert ppf_net_contributions_from_ledger(session, hid) == pytest.approx(577_500.0)
    assert holding_cost_basis(session, h) == pytest.approx(577_500.0)
