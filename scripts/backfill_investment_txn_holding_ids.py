#!/usr/bin/env python3
"""
Backfill ``investment_transactions.holding_id`` for rows that were inserted before
linking existed, or when holdings were imported later than ledger CSVs.

Run from repo root::

    python3 scripts/backfill_investment_txn_holding_ids.py
    python3 scripts/backfill_investment_txn_holding_ids.py --user-id sashank
    python3 scripts/backfill_investment_txn_holding_ids.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from sqlmodel import Session  # noqa: E402

from api.database import get_engine, init_db  # noqa: E402
from pipeline.investment_txn_linking import link_unlinked_investment_transactions  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--user-id",
        default=None,
        help="Limit to holdings owned by this user (default: all owners in holdings)",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be linked but roll back (no commit).",
    )
    args = p.parse_args()

    init_db()
    engine = get_engine()
    uids = [args.user_id.strip()] if args.user_id and args.user_id.strip() else None

    with Session(engine) as session:
        stats = link_unlinked_investment_transactions(session, user_ids=uids)
        print(
            "examined={examined} linked={linked} still_orphan={still_orphan} ambiguous={ambiguous}".format(
                examined=stats["examined"],
                linked=stats["linked"],
                still_orphan=stats["still_orphan"],
                ambiguous=stats["ambiguous"],
            )
        )
        if args.dry_run:
            session.rollback()
            print("(dry-run — rolled back)")
        else:
            session.commit()
            print("Committed.")


if __name__ == "__main__":
    main()
