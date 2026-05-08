#!/usr/bin/env python3
"""
One-shot remediation: align holdings with investment_transactions, then load historical prices.

Use after upgrading Arth when broker holdings showed stale quantities (e.g. sold stocks
still active). Same logic as POST /api/onboarding/portfolio-derive + background price job,
but runs synchronously for one user.

Usage::

    APP_ENV=prod python3 scripts/remediate_onboarding_portfolio.py --user-id sashank

Historical price import can take several minutes (NSE/MF network calls).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("remediate_onboarding_portfolio")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--user-id", required=True, help="Arth username (holdings.user_id)")
    args = p.parse_args(argv)
    uid = str(args.user_id).strip()
    if not uid:
        raise SystemExit("--user-id must not be empty")

    from api.database import init_db

    init_db()

    from api.services.holdings_sync import sync_holdings_for_user
    from api.services.onboarding_price_backfill import run_onboarding_price_backfill_sync
    from sqlmodel import Session

    from api.database import get_engine

    engine = get_engine()
    with Session(engine) as session:
        out = sync_holdings_for_user(session, uid)
        session.commit()
        logger.info("sync_holdings_for_user: %s", out)

    summary = run_onboarding_price_backfill_sync(uid)
    logger.info("price backfill summary: %s", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
