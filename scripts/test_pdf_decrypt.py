#!/usr/bin/env python3
"""
Phase 0e — Proof-of-concept: Gmail → PDF attachment → decrypt → first page text.

Before building the four statement parsers, this script answers: *Can we reliably
pull the encrypted PDF from Gmail and open it with the right password?*

Subject-line reference (monthly vs annual ICICI, three demat variants): see
``docs/personal-data/email-parsers-subject.txt``.

Steps (for each probe below):
  1. Search Gmail for one recent email matching a subject-style query.
  2. Download PDF attachment(s) via :meth:`scraper.gmail_client.GmailClient.get_attachments`.
  3. Decrypt with :func:`scraper.pdf_utils.decrypt_pdf` using the password from ``.env``.
  4. Print the first page of text via pdfplumber (sanity check that the file is readable).

Usage (from repo root, with ``.env`` containing the ``*_PASSWORD`` vars):

    python3 scripts/test_pdf_decrypt.py

Requires: Gmail OAuth already completed (``data/gmail_token.json``).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Repo root on ``sys.path`` so ``import scraper`` works when run as a script.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pipeline.config  # noqa: E402, F401 — loads ``.env`` via `load_dotenv()`

import pdfplumber  # noqa: E402

from scraper.gmail_client import GmailClient  # noqa: E402
from scraper.pdf_utils import decrypt_pdf  # noqa: E402


def _password_from_env(*env_names: str) -> str:
    """Return the first non-empty env value (lets us support legacy var names)."""
    for name in env_names:
        v = os.getenv(name, "").strip()
        if v:
            return v
    return ""


# Each row: label, Gmail ``q`` fragment (combined with ``after:``), env var name(s) for the PDF password.
# ICICI monthly vs annual differ in subject *and* password; demat has two password families (ICICI vs NSE).
# Tweak queries if your bank reworded subjects — see docs/personal-data/email-parsers-subject.txt.
PROBES: list[tuple[str, str, tuple[str, ...]]] = [
    (
        "HDFC Combined monthly statement",
        'subject:"HDFC Bank Combined Email Statement"',
        ("HDFC_STATEMENT_PASSWORD",),
    ),
    (
        "ICICI monthly savings statement",
        # Doc: "ICICI Bank Statement from ..." (monthly)
        'subject:"ICICI Bank Statement from"',
        ("ICICI_STATEMENT_MONTHLY_PASSWORD", "ICICI_STATEMENT_PASSWORD"),
    ),
    (
        "ICICI annual savings statement (incl. PPF section in PDF)",
        # Sender is customernotification@icicibank.com (not the same as InstaAlert .bank.in).
        # Subject example: "Bank Statement from 01-01-2025 to 31-12-2025 for …XXXX18"
        'from:customernotification@icicibank.com subject:"Bank Statement from"',
        ("ICICI_STATEMENT_ANNUAL_PASSWORD",),
    ),
    (
        "HDFC CC — Swiggy card",
        'subject:"Swiggy" subject:"Credit Card Statement"',
        ("HDFC_CC_STATEMENT_PASSWORD",),
    ),
    (
        "HDFC CC — Diners",
        'subject:"Diners Privilege" subject:"Credit Card Statement"',
        ("HDFC_CC_STATEMENT_PASSWORD",),
    ),
    (
        "ICICI Direct — NSE Equity Digital Contract Note (ICICI email / password)",
        'subject:"NSE Equity Digital Contract Note"',
        ("ICICI_DIRECT_EMAIL_PASSWORD", "ICICI_DIRECT_TRADE_PASSWORD"),
    ),
    (
        "ICICI Direct — Order and Trade confirmations (ICICI email / password)",
        'subject:"Order and Trade confirmations"',
        ("ICICI_DIRECT_EMAIL_PASSWORD", "ICICI_DIRECT_TRADE_PASSWORD"),
    ),
    (
        "ICICI Direct — Trades executed at NSE (NSE email / different PDF password)",
        'subject:"Trades executed at NSE"',
        ("NSE_TRADES_EXECUTED_PASSWORD", "ICICI_DIRECT_TRADE_PASSWORD"),
    ),
]


def _first_page_text(pdf_path: Path) -> str:
    """Extract plain text from page 1 for a quick eyeball check."""
    with pdfplumber.open(pdf_path) as pdf:
        if not pdf.pages:
            return ""
        return pdf.pages[0].extract_text() or ""


def main() -> None:
    print("Phase 0e — PDF decrypt POC\n")

    client = GmailClient()
    client.authenticate()
    print("Gmail: OK\n")

    after = "2015/01/01"

    for label, q_fragment, pwd_envs in PROBES:
        print("─" * 72)
        print(f"{label}")
        print(f"  Query: {q_fragment} after:{after}")

        password = _password_from_env(*pwd_envs)
        if not password:
            joined = " or ".join(pwd_envs)
            print(f"  SKIP — set one of: {joined}\n")
            continue

        query = f"{q_fragment} after:{after}"
        matches = client.search_messages(query, paginate=False, max_results_per_page=5)
        if not matches:
            print("  SKIP — no emails matched (adjust query or check mailbox).\n")
            continue

        msg = matches[0]
        print(f"  Using message {msg.id} | {msg.received_at.date()} | {msg.subject[:70]}")

        pdfs = client.get_attachments(msg.id)
        if not pdfs:
            print("  FAIL — no PDF attachments on this message.\n")
            continue

        name, raw = pdfs[0]
        print(f"  Attachment: {name} ({len(raw):,} bytes)")

        out: Path | None = None
        try:
            out = decrypt_pdf(raw, password=password)
            snippet = _first_page_text(out)[:1200]
            print("  Decrypt: OK")
            print("  First page (excerpt):")
            print("  " + "\n  ".join(snippet.splitlines()[:25]))
            if len(snippet) >= 1200:
                print("  [... truncated ...]")
        except Exception as exc:
            print(f"  FAIL — {exc!r}")
        finally:
            if out is not None:
                out.unlink(missing_ok=True)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
