"""Repair ISIN-keyed holdings before portfolio price backfill."""

from __future__ import annotations


import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from api.models import Holding
from api.services.historical_portfolio import (
    historical_price_symbol_universe,
    repair_isin_symbol_holdings,
)
from pipeline.models import AssetClass, ValuationMethod


@pytest.fixture(name="engine")
def _engine():
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(eng)
    yield eng
    SQLModel.metadata.drop_all(eng)
    eng.dispose()


def test_repair_isin_holding_rewrites_symbol_for_price_universe(
    engine: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    isin = "INE002A01018"
    with Session(engine) as session:
        session.add(
            Holding(
                symbol=isin,
                name="Reliance",
                asset_class=AssetClass.EQUITY.value,
                account_platform="ICICI Direct",
                valuation_method=ValuationMethod.MARKET_PRICE.value,
                liquidity_class="LIQUID",
                user_id="u1",
                is_active=True,
            )
        )
        session.commit()

    from pipeline import isin_nse_resolver

    monkeypatch.setattr(
        isin_nse_resolver,
        "_load_map",
        lambda: {isin: {"symbol": "RELIANCE", "name": "RELIANCE", "last_seen": "2026-01-01"}},
    )
    monkeypatch.setattr(
        isin_nse_resolver,
        "lookup_isin_symbol",
        lambda iso: "RELIANCE" if iso.upper() == isin else None,
    )

    with Session(engine) as session:
        n = repair_isin_symbol_holdings(session, user_id="u1")
        session.commit()
        assert n == 1
        h = session.exec(select(Holding).where(Holding.user_id == "u1")).first()
        assert h is not None
        assert h.symbol == "RELIANCE"
        universe = historical_price_symbol_universe(session, user_id="u1")
        assert "RELIANCE" in universe["nse_symbols"]
        assert isin not in universe["nse_symbols"]
