"""Unit tests for ``scraper.onboarding_orchestrator`` (chunk backfill, thresholds).

Uses in-memory SQLite plus mocks for Gmail and email parsing so nothing hits the
network. This mirrors the strategy in ``test_orchestrator.py``.
"""

from __future__ import annotations

import datetime
from unittest.mock import patch

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from api.models import Transaction
from scraper.config_loader import BankSendersConfig
from scraper.gmail_client import GmailMessage
from scraper.onboarding_orchestrator import (
    count_classification_unknowns,
    run_onboarding_backfill,
    sender_emails_for_source_key,
    pause_backfill_state,
    resume_backfill_state,
)

# Minimal static config shaped like ``BANK_SENDERS`` (one savings source).
_MINI_BANK: BankSendersConfig = {
    "alerts@hdfcbank.net": {
        "display_name": "HDFC",
        "source_type": "savings",
        "expected_cadence": "monthly",
        "accounts": {
            "3703": {"account_id": "HDFC_SAL_3703", "source_key": "hdfc_savings_test"},
        },
    },
    "alerts@hdfcbank.bank.in": {
        "display_name": "HDFC",
        "source_type": "savings",
        "expected_cadence": "per_transaction",
        "accounts": {
            "3703": {"account_id": "HDFC_SAL_3703", "source_key": "hdfc_savings_test"},
        },
    },
}


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
def _session(engine: object):
    with Session(engine) as s:
        yield s


def test_sender_emails_for_source_key_sorted_unique() -> None:
    out = sender_emails_for_source_key(_MINI_BANK, "hdfc_savings_test")
    assert out == [
        "alerts@hdfcbank.bank.in",
        "alerts@hdfcbank.net",
    ]


def _make_unknown_email_txn(
    *,
    i: int,
    user: str = "u1",
    source: str = "hdfc_savings_test",
) -> Transaction:
    """A row that still counts as a classification 'unknown' (OUTFLOW, spend unset)."""
    h = f"u{i:060x}"  # unique 64+ hex for content_hash
    return Transaction(
        content_hash="h" + h,
        txn_date=datetime.date(2024, 1, 1),
        account_id="HDFC_SAL_3703",
        user_id=user,
        source_statement=source,
        source_type="email",
        direction="OUTFLOW",
        amount=1.0,
        raw_description=f"UPI {i}",
        txn_type="UPI_EXPENSE",
        channel="UPI",
        counterparty=None,  # unknown → counted
        counterparty_category=None,
    )


def test_count_classification_unknowns_increments(
    session: Session,
) -> None:
    session.add(_make_unknown_email_txn(i=1))
    session.add(_make_unknown_email_txn(i=2))
    session.commit()
    n = count_classification_unknowns(session, user_id="u1", source_key="hdfc_savings_test")
    assert n == 2


@patch("scraper.onboarding_orchestrator.get_bank_senders_config", return_value=_MINI_BANK)
@patch("scraper.onboarding_orchestrator._process_email", return_value=("processed", 1))
def test_run_onboarding_backfill_processes_chunk(
    _proc,
    _bank,
    session: Session,
) -> None:
    """One chunk drains messages, updates progress, then completes the queue."""
    t0 = datetime.date(2010, 1, 1)
    t1 = datetime.date.today() + datetime.timedelta(days=1)
    m1 = GmailMessage(
        id="mid1",
        thread_id="th1",
        sender="alerts@hdfcbank.net",
        subject="x",
        received_at=datetime.datetime(2024, 1, 1, tzinfo=datetime.timezone.utc),
    )
    m2 = GmailMessage(
        id="mid2",
        thread_id="th2",
        sender="alerts@hdfcbank.net",
        subject="x",
        received_at=datetime.datetime(2024, 1, 2, tzinfo=datetime.timezone.utc),
    )

    class _FakeGmail:
        def search_messages(self, query, **kwargs):
            assert "from:alerts@" in query
            assert "after:" in query
            return [m1, m2]

        def fetch_message_by_id(self, message_id: str) -> GmailMessage:
            return m1 if message_id == "mid1" else m2

    with patch("scraper.onboarding_orchestrator._record_email"), patch(
        "scraper.onboarding_orchestrator._get_processed_ids", return_value=set()
    ):
        g = _FakeGmail()
        r1 = run_onboarding_backfill(
            session=session,
            user_id="u1",
            source_key="hdfc_savings_test",
            gmail_client=g,  # type: ignore[arg-type]
            existing_progress={},
            chunk_size=1,
            after=t0,
            before=t1,
            unknown_threshold=10_000,
        )
    p1 = r1.progress
    assert p1.get("emails_found") == 2
    assert p1.get("emails_processed") == 1
    assert p1.get("status") == "processing_statements"

    with patch("scraper.onboarding_orchestrator._record_email"), patch(
        "scraper.onboarding_orchestrator._get_processed_ids", return_value=set()
    ):
        r2 = run_onboarding_backfill(
            session=session,
            user_id="u1",
            source_key="hdfc_savings_test",
            gmail_client=g,  # type: ignore[arg-type]
            existing_progress=p1,
            chunk_size=1,
            after=t0,
            before=t1,
            unknown_threshold=10_000,
        )
    p2 = r2.progress
    assert p2.get("emails_processed") == 2
    assert p2.get("status") == "complete"


@patch("scraper.onboarding_orchestrator.get_bank_senders_config", return_value=_MINI_BANK)
@patch("scraper.onboarding_orchestrator._process_email", return_value=("processed", 0))
def test_run_onboarding_backfill_pauses_on_unknown_threshold(
    _proc,
    _bank,
    session: Session,
) -> None:
    """When DB unknowns for the source meet ``unknown_threshold``, status is ``needs_classification``."""
    t0 = datetime.date(2010, 1, 1)
    t1 = datetime.date.today() + datetime.timedelta(days=1)
    m1 = GmailMessage(
        id="sole",
        thread_id="th",
        sender="alerts@hdfcbank.net",
        subject="s",
        received_at=datetime.datetime(2024, 6, 1, tzinfo=datetime.timezone.utc),
    )
    for i in range(3):
        session.add(_make_unknown_email_txn(i=i))
    session.commit()

    class _FakeGmail:
        def search_messages(self, _query, **kwargs):
            return [m1]

        def fetch_message_by_id(self, _mid: str) -> GmailMessage:
            return m1

    g = _FakeGmail()
    with patch("scraper.onboarding_orchestrator._record_email"), patch(
        "scraper.onboarding_orchestrator._get_processed_ids", return_value=set()
    ):
        r = run_onboarding_backfill(
            session=session,
            user_id="u1",
            source_key="hdfc_savings_test",
            gmail_client=g,  # type: ignore[arg-type]
            existing_progress={},
            chunk_size=1,
            after=t0,
            before=t1,
            unknown_threshold=3,
        )
    assert r.progress.get("status") == "needs_classification"
    assert int(r.progress.get("unknowns_pending") or 0) >= 3


def test_pause_resume_state_helpers() -> None:
    s = {"status": "processing", "emails_processed": 5}
    p = pause_backfill_state(s)
    assert p["status"] == "paused"
    r = resume_backfill_state(p)
    assert r["status"] == "processing"
