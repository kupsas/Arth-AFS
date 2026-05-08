#!/usr/bin/env python3
"""
One-time migration: seed ``scraper_bank_senders`` + ``scraper_account_mappings`` from
the legacy account map that used to live in ``scraper/config.py``, and seed
``user_pipeline_sources`` from the legacy ``SOURCE_CONFIGS`` in ``pipeline/config.py``.

Run after pulling the repo version where ``BANK_SENDERS`` no longer embeds personal
last-4 / account_id rows — this script carries that snapshot so your local SQLite
gets the same mappings ``get_bank_senders_config`` used to infer from code.

Usage:
    python scripts/migrate_sashank_config_to_db.py           # user_id=sashank
    python scripts/migrate_sashank_config_to_db.py --dry-run
    python scripts/migrate_sashank_config_to_db.py --user-id otheruser

Requires the app database (see ``pipeline.config.DB_PATH``).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Repo root on sys.path
_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("migrate_sashank_config")

# ─── Legacy per-account maps (previously in scraper/config.py) ─────────────
# These values are the same ones that lived in version control before the
# email-import overhaul; they are loaded into SQLite so ``config.py`` can stay generic.

_LEGACY_HDFC_BANK_ACCOUNTS: dict[str, dict[str, str]] = {
    "3703": {"account_id": "HDFC_SAL_3703", "source_key": "hdfc_savings"},
    "1905": {"account_id": "HDFC_CC_1905", "source_key": "hdfc_cc_1905"},
    "5778": {"account_id": "HDFC_CC_5778", "source_key": "hdfc_cc_5778"},
}

_LEGACY_ICICI_STATEMENT_ACCOUNTS: dict[str, dict[str, str]] = {
    "6118": {"account_id": "ICICI_SAV_6118", "source_key": "icici_savings"},
}

_LEGACY_HDFC_CC_STATEMENT_ACCOUNTS: dict[str, dict[str, str]] = {
    "1905": _LEGACY_HDFC_BANK_ACCOUNTS["1905"],
    "5778": _LEGACY_HDFC_BANK_ACCOUNTS["5778"],
}

_LEGACY_ICICI_DIRECT_BROKER_ACCOUNTS: dict[str, dict[str, str]] = {
    "0000": {"account_id": "ICICI_DIRECT", "source_key": "icici_direct_statement"},
}

# sender_email -> accounts dict (merged with live BANK_SENDERS metadata in migrate())
_LEGACY_ACCOUNTS_BY_SENDER: dict[str, dict[str, dict[str, str]]] = {
    "alerts@hdfcbank.net": _LEGACY_HDFC_BANK_ACCOUNTS,
    "alerts@hdfcbank.bank.in": _LEGACY_HDFC_BANK_ACCOUNTS,
    "customernotification@icici.bank.in": _LEGACY_ICICI_STATEMENT_ACCOUNTS,
    "estatement@icicibank.com": _LEGACY_ICICI_STATEMENT_ACCOUNTS,
    "estatement@icici.bank.in": _LEGACY_ICICI_STATEMENT_ACCOUNTS,
    "customernotification@icicibank.com": _LEGACY_ICICI_STATEMENT_ACCOUNTS,
    "emailstatements.cards@hdfcbank.net": _LEGACY_HDFC_CC_STATEMENT_ACCOUNTS,
    "emailstatements.cards@hdfcbank.bank.in": _LEGACY_HDFC_CC_STATEMENT_ACCOUNTS,
    "hdfcbanksmartstatement@hdfcbank.net": {"3703": _LEGACY_HDFC_BANK_ACCOUNTS["3703"]},
    "hdfcbanksmartstatement@hdfcbank.bank.in": {"3703": _LEGACY_HDFC_BANK_ACCOUNTS["3703"]},
    "service@icicisecurities.com": _LEGACY_ICICI_DIRECT_BROKER_ACCOUNTS,
}

# ─── Legacy file-pipeline sources (previously in pipeline/config.py SOURCE_CONFIGS) ─
_LEGACY_PIPELINE_SOURCES: list[dict[str, str]] = [
    {
        "source_key": "hdfc_savings",
        "account_id": "HDFC_SAL_3703",
        "statement_folder": "HDFC_Savings",
    },
    {
        "source_key": "hdfc_cc_1905",
        "account_id": "HDFC_CC_1905",
        "statement_folder": "1905_CC",
    },
    {
        "source_key": "hdfc_cc_5778",
        "account_id": "HDFC_CC_5778",
        "statement_folder": "5778_CC",
    },
    {
        "source_key": "icici_savings",
        "account_id": "ICICI_SAV_6118",
        "statement_folder": "ICICI_Savings",
    },
]


def _merge_bank_config_for_user() -> dict[str, dict]:
    """Full BANK_SENDERS-shaped dict: metadata from code + accounts from legacy snapshot."""
    from scraper.config import BANK_SENDERS

    out: dict[str, dict] = {}
    for sender, cfg in BANK_SENDERS.items():
        key = sender.strip().lower()
        merged = dict(cfg)
        merged["accounts"] = dict(
            _LEGACY_ACCOUNTS_BY_SENDER.get(key, cfg.get("accounts") or {})
        )
        out[key] = merged
    return out


def migrate(*, user_id: str, dry_run: bool) -> int:
    from sqlmodel import Session, select

    from api.database import get_engine
    from api.models import ScraperAccountMapping, ScraperBankSender, UserPipelineSource
    from api.services.family_member_utils import self_member_id

    bank = _merge_bank_config_for_user()
    engine = get_engine()

    with Session(engine) as session:
        mid = self_member_id(session, user_id)

        plan_senders: list[tuple[str, dict]] = []
        for sender_email, cfg in sorted(bank.items()):
            key = sender_email.strip().lower()
            plan_senders.append((key, cfg))

        if dry_run:
            logger.info(
                "[dry-run] Would upsert %d senders + mappings for user_id=%r",
                len(plan_senders),
                user_id,
            )
            for key, cfg in plan_senders:
                n_acct = len(cfg.get("accounts") or {})
                logger.info("  %s  accounts=%d  parser_key=%r", key, n_acct, cfg.get("parser_key"))
            logger.info(
                "[dry-run] Would replace user_pipeline_sources with %d rows for user_id=%r",
                len(_LEGACY_PIPELINE_SOURCES),
                user_id,
            )
            for spec in _LEGACY_PIPELINE_SOURCES:
                logger.info(
                    "  %s -> account_id=%r folder=%r",
                    spec["source_key"],
                    spec["account_id"],
                    spec["statement_folder"],
                )
            return 0

        # Remove prior scraper rows for this user so we match legacy snapshot exactly.
        for row in session.exec(
            select(ScraperAccountMapping).where(ScraperAccountMapping.user_id == user_id)
        ).all():
            session.delete(row)
        for row in session.exec(
            select(ScraperBankSender).where(ScraperBankSender.user_id == user_id)
        ).all():
            session.delete(row)
        session.commit()

        for key, cfg in plan_senders:
            pats = cfg.get("discovery_subject_patterns")
            meta_json = json.dumps(pats) if isinstance(pats, list) else None
            session.add(
                ScraperBankSender(
                    user_id=user_id,
                    sender_email=key,
                    parser_key=str(cfg["parser_key"]) if cfg.get("parser_key") else None,
                    first_run_lookback_days=cfg.get("first_run_lookback_days"),
                    enabled=True,
                    display_name=cfg.get("display_name"),
                    instrument_type=cfg.get("instrument_type"),
                    expected_cadence=cfg.get("expected_cadence"),
                    discovery_subject_patterns_json=meta_json,
                )
            )
            for last_4, acct in (cfg.get("accounts") or {}).items():
                session.add(
                    ScraperAccountMapping(
                        user_id=user_id,
                        sender_email=key,
                        last_4_digits=str(last_4),
                        account_id=str(acct["account_id"]),
                        source_key=str(acct["source_key"]),
                        member_id=mid,
                    )
                )
        session.commit()
        logger.info(
            "Seeded scraper_bank_senders + scraper_account_mappings for user_id=%r (%d senders).",
            user_id,
            len(plan_senders),
        )

        for row in session.exec(
            select(UserPipelineSource).where(UserPipelineSource.user_id == user_id)
        ).all():
            session.delete(row)
        for spec in _LEGACY_PIPELINE_SOURCES:
            session.add(
                UserPipelineSource(
                    user_id=user_id,
                    source_key=spec["source_key"],
                    account_id=spec["account_id"],
                    currency="INR",
                    statement_folder=spec["statement_folder"],
                )
            )
        session.commit()
        logger.info(
            "Seeded user_pipeline_sources for user_id=%r (%d sources).",
            user_id,
            len(_LEGACY_PIPELINE_SOURCES),
        )
    return 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user-id", default="sashank", help="Arth username (default: sashank)")
    ap.add_argument("--dry-run", action="store_true", help="Print plan only; do not write DB")
    args = ap.parse_args()
    uid = (args.user_id or "").strip() or "sashank"
    raise SystemExit(migrate(user_id=uid, dry_run=bool(args.dry_run)))


if __name__ == "__main__":
    main()
