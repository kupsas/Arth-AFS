"""
Unit / API tests for onboarding batch classification (Track 2 Phase 3b).

The FastAPI :func:`~api.routes.onboarding.onboarding_classify` path updates
transactions and optionally inserts :class:`api.models.UserMerchantRule` rows
with ``source=USER_CORRECTION``.
"""

from __future__ import annotations

import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from api.auth import get_current_user
from api.database import get_session
from api.main import app
from api.models import Transaction, UserMerchantRule
from importlib import import_module


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


@pytest.fixture(name="onboarding_test_client")
def _onboarding_test_client(
    engine: object, monkeypatch: pytest.MonkeyPatch
) -> Any:
    """``TestClient`` with the same in-memory + auth override pattern as ``test_db_and_api``."""
    from api import database as _db_mod

    _orig_init = _db_mod.init_db
    _db_mod.init_db = lambda: None

    def _override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: "batch_user"

    with TestClient(app) as c:
        yield c

    _db_mod.init_db = _orig_init
    app.dependency_overrides.clear()
    # Avoid leaking a lowered LLM threshold into other test modules
    _pc = import_module("pipeline.config")
    monkeypatch.setattr(_pc, "LLM_MODEL", "auto", raising=False)


def _seed_user_and_txn(session: Session) -> int:
    t = Transaction(
        content_hash="batch_hash_01",
        txn_date=datetime.date(2024, 5, 1),
        account_id="ACC",
        user_id="batch_user",
        source_statement="src_a",
        source_type="email",
        direction="OUTFLOW",
        amount=99.0,
        raw_description="UPI SWIGGY SWIGGY",
        channel="UPI",
        is_reviewed=False,
    )
    session.add(t)
    session.commit()
    session.refresh(t)
    return int(t.id or 0)


def test_onboarding_classify_updates_txn_and_creates_rule(
    engine: object,
    onboarding_test_client: TestClient,
) -> None:
    with Session(engine) as session:
        txn_id = _seed_user_and_txn(session)

    body = {
        "source": "src_a",
        "items": [
            {
                "txn_id": txn_id,
                "counterparty": "Swiggy",
                "counterparty_category": "Swiggy",
                "spend_category": "WANT",
                "apply_to_future": True,
                "merchant_rule_keyword": "SWIGGY",
            }
        ],
    }
    r = onboarding_test_client.post("/api/onboarding/classify", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["status"] == "ok"
    assert data["rules_upserted"] == 1

    with Session(engine) as session:
        row = session.get(Transaction, txn_id)
        assert row is not None
        assert row.counterparty == "Swiggy"
        assert row.spend_category == "WANT"
        assert row.classification_source == "USER_REVIEWED"
        ur = session.exec(
            select(UserMerchantRule).where(
                UserMerchantRule.user_id == "batch_user",
                UserMerchantRule.keyword == "SWIGGY",
            )
        ).first()
        assert ur is not None
        assert ur.source == "USER_CORRECTION"
        assert ur.display_name == "Swiggy"


def test_onboarding_classify_rejects_wrong_source(
    engine: object,
    onboarding_test_client: TestClient,
) -> None:
    with Session(engine) as session:
        txn_id = _seed_user_and_txn(session)
    r = onboarding_test_client.post(
        "/api/onboarding/classify",
        json={
            "source": "other_source",
            "items": [
                {
                    "txn_id": txn_id,
                    "counterparty": "X",
                    "counterparty_category": "X",
                }
            ],
        },
    )
    assert r.status_code == 400
