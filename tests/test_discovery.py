"""Unit tests for ``scraper.discovery`` — Gmail source discovery (Track 2 Phase 2a).

We mock :class:`scraper.gmail_client.GmailClient` so tests never call the real Gmail API.
"""

from __future__ import annotations

import datetime
from unittest.mock import MagicMock

from scraper.discovery import DiscoveredSource, discover_sources, discovered_sources_to_json
from scraper.gmail_client import GmailMessage


def _msg(
    i: int,
    *,
    subject: str = "Account alert",
    day: int = 1,
) -> GmailMessage:
    """Build a small :class:`GmailMessage` for list probes."""
    return GmailMessage(
        id=f"m{i}",
        thread_id=f"t{i}",
        sender="alerts@bank.test",
        subject=subject,
        received_at=datetime.datetime(2024, 3, day, 12, 0, 0, tzinfo=datetime.timezone.utc),
    )


def test_discover_sources_empty_mailbox() -> None:
    """When Gmail returns no rows for a sender, estimate is 0 and dates are None."""
    client = MagicMock()
    client.search_messages.return_value = []

    bank = {
        "nobody@example.com": {
            "display_name": "Empty Bank",
            "source_type": "savings",
        }
    }
    out = discover_sources(client, bank, existence_sample_size=3)
    assert len(out) == 1
    r = out[0]
    assert r.sender_email == "nobody@example.com"
    assert r.email_count_estimate == 0
    assert r.earliest_email_date is None
    assert r.latest_email_date is None
    client.search_messages.assert_called()


def test_discover_sources_finds_email_and_volume_estimate() -> None:
    """With one sample page of messages, dates are min/max of that page; estimate is capped scan."""
    client = MagicMock()
    # First call: non-paginated probe (per sender)
    sample = [_msg(1, day=5), _msg(2, day=20)]
    full_page = sample * 2  # paginated estimate path returns 4 (<= estimate_cap)

    def _search(
        _query: str,
        *,
        paginate: bool = False,
        max_results_per_page: int = 100,
        max_total: int | None = None,
    ):
        if not paginate:
            return sample
        # Capped volume sweep
        return full_page[: max_total or len(full_page)]

    client.search_messages.side_effect = _search

    bank = {
        "alerts@hdfcbank.net": {
            "display_name": "HDFC Test",
            "source_type": "savings",
        }
    }
    out = discover_sources(client, bank, estimate_cap=100)
    assert len(out) == 1
    r = out[0]
    assert r.email_count_estimate == len(full_page)
    assert r.earliest_email_date == datetime.date(2024, 3, 5)
    assert r.latest_email_date == datetime.date(2024, 3, 20)


def test_discover_sources_subject_filter_requires_regex_match() -> None:
    """``subject_patterns_must_match_sample`` drops non-matching subjects from the small sample."""
    client = MagicMock()
    # Probe page: one InstaAlert (matches) and one marketing email (dropped)
    m_ok = _msg(1, subject="InstaAlert: UPI")
    m_bad = _msg(2, subject="We miss you — apply for a loan")
    client.search_messages.return_value = [m_ok, m_bad]

    bank = {
        "bank@test.in": {
            "display_name": "Filtered",
            "source_type": "savings",
            "discovery_subject_patterns": [r"InstaAlert"],
        }
    }
    out = discover_sources(
        client,
        bank,
        subject_patterns_must_match_sample=True,
        estimate_cap=20,
    )
    assert len(out) == 1
    r = out[0]
    # After filter only one message remains, so min == max == that day
    assert r.earliest_email_date == datetime.date(2024, 3, 1)
    assert r.latest_email_date == datetime.date(2024, 3, 1)


def test_discovered_sources_to_json_round_trip() -> None:
    """JSON helper matches API contract (ISO dates, no surprise types)."""
    row = DiscoveredSource(
        sender_email="a@b.com",
        display_name="Bank",
        source_type="savings",
        email_count_estimate=3,
        earliest_email_date=datetime.date(2022, 1, 2),
        latest_email_date=datetime.date(2022, 6, 1),
    )
    payload = discovered_sources_to_json([row])[0]
    assert payload["sender_email"] == "a@b.com"
    assert payload["earliest_email_date"] == "2022-01-02"
    assert payload["email_count_estimate"] == 3
