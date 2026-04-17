"""Tests for :mod:`api.services.nse_equity_reference` (index + bhav snapshot, no live NSE)."""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import api.models  # noqa: F401 — register all ORM tables for create_all

from api.models import NseEquityReference
from api.services.nse_equity_reference import refresh_nse_equity_reference


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


def test_refresh_partitions_large_mid_small(monkeypatch: pytest.MonkeyPatch, engine) -> None:
    from api.services import nse_equity_reference as mod

    monkeypatch.setattr(mod.time, "sleep", lambda *_a, **_k: None)

    def fake_resolve(preferred: datetime.date):
        return datetime.date(2025, 1, 15), {"DUMMY": 1.0}

    monkeypatch.setattr(mod, "resolve_nse_bhav_session_and_map", fake_resolve)
    monkeypatch.setattr(
        mod,
        "load_nse_equity_bhav_full_rows",
        lambda _d: {
            "RELIANCE": {"CLSPRIC": "2500"},
            "TINYCAP": {"CLSPRIC": "1"},
        },
    )

    class FakeNse:
        def listEquityStocksByIndex(self, name: str) -> dict:
            if name == "NIFTY 100":
                return {
                    "data": [
                        {
                            "symbol": "RELIANCE",
                            "lastPrice": 2500,
                            "ffmc": 1e12,
                            "meta": {
                                "symbol": "RELIANCE",
                                "companyName": "Reliance Industries Limited",
                                "industry": "Oil",
                                "isin": "INE002A01018",
                            },
                        }
                    ]
                }
            if name == "NIFTY MIDCAP 150":
                return {
                    "data": [
                        {
                            "symbol": "MIDCO",
                            "lastPrice": 100,
                            "meta": {
                                "symbol": "MIDCO",
                                "companyName": "Mid Company",
                                "industry": "Textiles",
                                "isin": "INE999A01012",
                            },
                        }
                    ]
                }
            return {"data": []}

    monkeypatch.setattr(mod, "get_nse_client", lambda: FakeNse())

    with Session(engine) as session:
        stats = refresh_nse_equity_reference(session, commit=True)

    assert stats["large_cap"] == 1
    assert stats["mid_cap"] == 1
    assert stats["small_cap"] == 1
    assert stats["symbols_total"] == 3

    with Session(engine) as session:
        r1 = session.get(NseEquityReference, "RELIANCE")
        r2 = session.get(NseEquityReference, "MIDCO")
        r3 = session.get(NseEquityReference, "TINYCAP")
    assert r1 is not None and r1.market_cap_class == "LARGE_CAP"
    assert r2 is not None and r2.market_cap_class == "MID_CAP"
    assert r3 is not None and r3.market_cap_class == "SMALL_CAP"
    assert r1.industry == "Oil"
    assert r3.market_cap_class == "SMALL_CAP"
