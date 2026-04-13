"""
Tests for Sub-Plan C — liquidity service and /api/liquidity routes.
"""

from __future__ import annotations

import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from api.auth import get_current_user
from api.database import get_session
from api.main import app
from api.models import Goal, Holding
from pipeline.models import AssetClass, LiquidityClass, ValuationMethod


@pytest.fixture(name="engine")
def in_memory_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture(name="session")
def db_session(engine):
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def api_client(engine):
    def _override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: "test_user"

    import api.database as _db_mod

    _original_init = _db_mod.init_db
    _db_mod.init_db = lambda: None

    with TestClient(app) as c:
        yield c

    _db_mod.init_db = _original_init
    app.dependency_overrides.clear()


def _seed_holding_and_goal(session: Session) -> tuple[int, int]:
    """One MF holding + one dated goal for test_user."""
    h = Holding(
        name="Test MF",
        symbol="123456",
        asset_class=AssetClass.MUTUAL_FUND.value,
        account_platform="ICICI Direct MF",
        valuation_method=ValuationMethod.MARKET_PRICE.value,
        liquidity_class=LiquidityClass.T_PLUS_3.value,
        user_id="test_user",
        current_value=100_000.0,
        is_active=True,
    )
    g = Goal(
        name="House down payment",
        goal_type="SAVINGS",
        user_id="test_user",
        target_date=datetime.date(2030, 6, 1),
        activation_status="ACTIVE",
        pyramid_id="PLQ1",
    )
    session.add(h)
    session.add(g)
    session.commit()
    session.refresh(h)
    session.refresh(g)
    assert h.id is not None and g.id is not None
    return h.id, g.id


def test_liquidity_summary_refresh_goal_match_suggestions_mismatch(
    client: TestClient, session: Session
) -> None:
    hid, gid = _seed_holding_and_goal(session)

    r0 = client.post("/api/liquidity/refresh?user_id=test_user")
    assert r0.status_code == 200
    body0 = r0.json()
    assert body0["user_id"] == "test_user"
    assert body0["holdings_examined"] == 1
    assert body0["updated"] >= 1

    r1 = client.get("/api/liquidity/summary?user_id=test_user")
    assert r1.status_code == 200
    s = r1.json()
    assert s["total_value_inr"] == 100_000.0
    assert len(s["buckets"]) == 7
    assert sum(b["total_value_inr"] for b in s["buckets"]) == pytest.approx(100_000.0)

    r2 = client.get(f"/api/liquidity/goal-match/{gid}?user_id=test_user")
    assert r2.status_code == 200
    m = r2.json()
    assert m["goal_id"] == gid
    assert len(m["matched_holdings"]) == 1
    assert m["matched_holdings"][0]["holding_id"] == hid
    assert m["total_accessible_value_inr"] == 100_000.0

    r3 = client.get("/api/liquidity/goal-suggestions?user_id=test_user")
    assert r3.status_code == 200
    sug = r3.json()
    assert len(sug) == 1
    assert sug[0]["goal_id"] == gid
    assert "2030-06-01" in sug[0]["explanation"]

    r4 = client.post(
        "/api/liquidity/mismatch-check?user_id=test_user",
        json={"goal_id": gid, "claimed_amount_inr": 500_000.0},
    )
    assert r4.status_code == 200
    mm = r4.json()
    assert mm["is_mismatch"] is True
    assert mm["shortfall_inr"] == pytest.approx(400_000.0)
    assert mm["warning_message"] is not None

    r5 = client.post(
        "/api/liquidity/mismatch-check?user_id=test_user",
        json={"goal_id": gid, "claimed_amount_inr": 50_000.0},
    )
    assert r5.status_code == 200
    ok = r5.json()
    assert ok["is_mismatch"] is False


def test_goal_match_404_wrong_user(client: TestClient, session: Session) -> None:
    _seed_holding_and_goal(session)
    r = client.get("/api/liquidity/goal-match/99999?user_id=test_user")
    assert r.status_code == 404
