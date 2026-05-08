"""Onboarding portfolio derivation includes holdings sync from ledger."""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("FERNET_KEY", Fernet.generate_key().decode("ascii"))

from api.services.onboarding_portfolio_derive import (  # noqa: E402
    run_onboarding_portfolio_derivation,
)


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


@pytest.fixture(name="session")
def _session(engine):
    with Session(engine) as s:
        yield s


def test_portfolio_derivation_returns_holdings_sync(session: Session) -> None:
    """Even with no broker ledger rows, derive/commit completes and reports sync stats."""
    out = run_onboarding_portfolio_derivation(session, "lonely_user_no_txns")
    assert "holdings_sync" in out
    sync = out["holdings_sync"]
    assert isinstance(sync, dict)
    assert sync.get("user_id") == "lonely_user_no_txns"
