#!/usr/bin/env python3
"""
Phase 0g — Historical depth: how far back does Gmail have statement emails?

For each statement *style* (subject query), this script:
  1. Paginates through **all** matching message IDs (uses ``search_messages(..., paginate=True)``).
  2. Reports **count** and the **oldest** ``received_at`` date.

ICICI has **two** savings statement subjects (monthly vs annual); demat has **three**
email shapes with two password families — see ``docs/personal-data/email-parsers-subject.txt``.

If counts go back many years, onboarding could theoretically ingest full history from
email alone (no manual uploads).

Usage:

    python3 scripts/test_email_depth.py

Requires Gmail OAuth (``data/gmail_token.json``).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pipeline.config  # noqa: E402, F401

from scraper.gmail_client import GmailClient  # noqa: E402

# Align queries with docs/personal-data/email-parsers-subject.txt — tweak if subjects change.
DEPTH_PROBES: list[tuple[str, str]] = [
    (
        "ICICI monthly savings statement",
        'subject:"ICICI Bank Statement from"',
    ),
    (
        "ICICI annual savings statement",
        'from:customernotification@icicibank.com subject:"Bank Statement from"',
    ),
    (
        "HDFC CC 1905 (Swiggy)",
        'subject:"Swiggy" subject:"Credit Card Statement"',
    ),
    (
        "HDFC CC 5778 (Diners)",
        'subject:"Diners Privilege" subject:"Credit Card Statement"',
    ),
    ("HDFC Combined Statement", 'subject:"HDFC Bank Combined Email Statement"'),
    (
        "ICICI Direct — NSE contract note (ICICI email)",
        'subject:"NSE Equity Digital Contract Note"',
    ),
    (
        "ICICI Direct — order/trade confirmations (ICICI email)",
        'subject:"Order and Trade confirmations"',
    ),
    (
        "ICICI Direct — trades at NSE (NSE email; different PDF password)",
        'subject:"Trades executed at NSE"',
    ),
]


def main() -> None:
    after = "2015/01/01"
    print(f"Gmail depth scan — messages matching each query with after:{after}\n")

    client = GmailClient()
    client.authenticate()

    # Column widths for a simple text table
    rows: list[tuple[str, str, str]] = []

    for label, q_fragment in DEPTH_PROBES:
        query = f"{q_fragment} after:{after}"
        messages = client.search_messages(
            query,
            paginate=True,
            max_results_per_page=500,
        )
        if not messages:
            rows.append((label, "—", "0"))
            continue
        oldest = min(m.received_at for m in messages)
        oldest_s = oldest.date().isoformat()
        rows.append((label, oldest_s, str(len(messages))))

    label_w = max(len(r[0]) for r in rows) if rows else 30
    print(f"{'Type':<{label_w}}  {'Oldest':<12}  Count")
    print(f"{'-' * label_w}  {'-' * 12}  -----")
    for label, oldest_s, count in rows:
        print(f"{label:<{label_w}}  {oldest_s:<12}  {count}")

    print("\nTip: empty or low counts usually mean the subject line changed — copy an")
    print("exact subject from Gmail search and update DEPTH_PROBES in this script.")


if __name__ == "__main__":
    main()
