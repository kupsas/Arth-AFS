"""
Synthetic ``accounts`` maps for email parser unit tests.

Production mappings live in SQLite (``scraper_account_mappings``); ``scraper.config.BANK_SENDERS``
keeps ``accounts: {}`` so fixtures must supply explicit last-4 → account_id rows here.
"""

from __future__ import annotations

# HDFC transaction-alert fixtures — matches ``tests/fixtures/email_samples/`` (3703 UPI, 1905 CC).
HDFC_ALERT_ACCOUNTS: dict[str, dict[str, str]] = {
    "3703": {"account_id": "HDFC_SAL_3703", "source_key": "hdfc_savings"},
    "1905": {"account_id": "HDFC_CC_1905", "source_key": "hdfc_cc_1905"},
    "5778": {"account_id": "HDFC_CC_5778", "source_key": "hdfc_cc_5778"},
}

ICICI_INSTA_ACCOUNTS: dict[str, dict[str, str]] = {
    "6118": {"account_id": "ICICI_SAV_6118", "source_key": "icici_savings"},
}

HDFC_CC_STATEMENT_ACCOUNTS: dict[str, dict[str, str]] = {
    "1905": {"account_id": "HDFC_CC_1905", "source_key": "hdfc_cc_1905"},
}

ICICI_STATEMENT_ACCOUNTS: dict[str, dict[str, str]] = {
    "6118": {"account_id": "ICICI_SAV_6118", "source_key": "icici_savings"},
}

HDFC_COMBINED_STATEMENT_ACCOUNTS: dict[str, dict[str, str]] = {
    "3703": {"account_id": "HDFC_SAL_3703", "source_key": "hdfc_savings"},
}
