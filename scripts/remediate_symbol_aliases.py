#!/usr/bin/env python3
"""
Remediate investment transactions whose symbol is a legacy ICICI broker alias
instead of the canonical NSE ticker.

For each alias → canonical pair in :data:`parsers.holdings.icici_direct_equity.ICICI_SHORT_TO_NSE`,
find ``investment_transaction`` rows whose ``symbol`` matches the alias and a ``holding`` with the
canonical symbol already exists for that user/platform. Merge: re-link the transactions, delete
the stale alias holding if it has no remaining transactions, then recompute the canonical holding
quantities via ``sync_holdings_for_user``.

Safe to re-run (idempotent). Use ``--dry-run`` first to preview.

Usage::

    python3 scripts/remediate_symbol_aliases.py --dry-run
    python3 scripts/remediate_symbol_aliases.py
    APP_ENV=onboarding python3 scripts/remediate_symbol_aliases.py
"""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from pipeline.config import DB_PATH  # noqa: E402
from parsers.holdings.icici_direct_equity import ICICI_SHORT_TO_NSE  # noqa: E402

logger = logging.getLogger(__name__)


def _all_aliases() -> dict[str, str]:
    """All alias → canonical pairs where alias != canonical (i.e. real renames)."""
    return {
        alias.upper(): canonical.upper()
        for alias, canonical in ICICI_SHORT_TO_NSE.items()
        if alias.upper() != canonical.upper()
    }


def remediate(db: Path, *, dry_run: bool) -> dict[str, int]:
    aliases = _all_aliases()
    alias_list = list(aliases.keys())
    if not alias_list:
        logger.info("No aliases defined — nothing to do.")
        return {"examined": 0, "relinked": 0, "holdings_deleted": 0}

    # SQLite timeout: wait up to 30 s for the write lock (uvicorn holds it in WAL mode briefly).
    conn = sqlite3.connect(str(db), timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()

        # Enable WAL mode so we can read alongside a running server.
        cur.execute("PRAGMA journal_mode=WAL")

        # Find all investment_transaction rows with an alias symbol.
        placeholders = ",".join("?" for _ in alias_list)
        txns = cur.execute(
            f"SELECT id, txn_date, txn_type, symbol, holding_id, account_platform "
            f"FROM investment_transactions WHERE UPPER(symbol) IN ({placeholders})",
            alias_list,
        ).fetchall()

        if not txns:
            logger.info("No alias investment_transaction rows found.")
            return {"examined": 0, "relinked": 0, "holdings_deleted": 0}

        logger.info("Found %d investment_transaction rows with alias symbols.", len(txns))

        relinked = 0
        stale_hids: set[int] = set()

        deleted_ids: set[int] = set()

        for row in txns:
            alias = (row["symbol"] or "").strip().upper()
            canonical = aliases.get(alias)
            if not canonical:
                continue

            old_hid: int | None = row["holding_id"]
            platform: str | None = row["account_platform"]

            # Identify user from the old holding.
            user_id: str | None = None
            if old_hid is not None:
                h_row = cur.execute(
                    "SELECT user_id FROM holdings WHERE id = ?", (old_hid,)
                ).fetchone()
                if h_row:
                    user_id = h_row["user_id"]
                    stale_hids.add(old_hid)

            # Find the canonical holding (may already exist or will exist after re-link).
            new_hid: int | None = None
            if user_id:
                canon_row = cur.execute(
                    "SELECT id FROM holdings WHERE user_id=? AND UPPER(symbol)=? AND account_platform=? LIMIT 1",
                    (user_id, canonical, platform),
                ).fetchone()
                if canon_row:
                    new_hid = canon_row["id"]

            # Check for a DUPLICATE: a canonical-symbol txn with same date, type, and qty
            # already linked to the canonical holding.  This happens when the same trade was
            # imported twice under different ticker labels (e.g. ICICINIFTY vs NIFTYIETF).
            is_dup = False
            if new_hid is not None:
                dup_row = cur.execute(
                    "SELECT id FROM investment_transactions "
                    "WHERE holding_id=? AND txn_date=? AND txn_type=? AND ABS(quantity - ?) < 0.0001 "
                    "AND id != ? LIMIT 1",
                    (new_hid, row["txn_date"], row["txn_type"], row["quantity"], row["id"]),
                ).fetchone()
                if dup_row:
                    is_dup = True

            if is_dup:
                logger.info(
                    "  txn id=%s date=%s type=%s  alias=%r → canonical=%r  "
                    "DUPLICATE (canonical txn already exists) — will delete%s",
                    row["id"], row["txn_date"], row["txn_type"],
                    alias, canonical,
                    "  (dry-run)" if dry_run else "",
                )
                if not dry_run:
                    cur.execute("DELETE FROM investment_transactions WHERE id=?", (row["id"],))
                    deleted_ids.add(row["id"])
            else:
                logger.info(
                    "  txn id=%s date=%s type=%s  alias=%r → canonical=%r  "
                    "old_holding=%s  new_holding=%s%s",
                    row["id"], row["txn_date"], row["txn_type"],
                    alias, canonical,
                    old_hid, new_hid if new_hid else "—",
                    "  (dry-run)" if dry_run else "",
                )
                if not dry_run:
                    cur.execute(
                        "UPDATE investment_transactions SET symbol=?, holding_id=? WHERE id=?",
                        (canonical, new_hid, row["id"]),
                    )
                    relinked += 1

        if dry_run:
            conn.rollback()
            return {"examined": len(txns), "relinked": 0, "holdings_deleted": 0}

        conn.commit()

        # Remove stale alias holdings that now have zero transactions.
        deleted = 0
        for hid in stale_hids:
            remaining = cur.execute(
                "SELECT COUNT(*) FROM investment_transactions WHERE holding_id=?", (hid,)
            ).fetchone()[0]
            if remaining == 0:
                h_row = cur.execute(
                    "SELECT id, symbol FROM holdings WHERE id=?", (hid,)
                ).fetchone()
                if h_row:
                    logger.info(
                        "  Deleting stale alias holding id=%s symbol=%r", h_row["id"], h_row["symbol"]
                    )
                    if not dry_run:
                        cur.execute("DELETE FROM holdings WHERE id=?", (hid,))
                        deleted += 1

        conn.commit()

        # Recompute qty / avg cost for canonical holdings.
        # We do this with a simple Python FIFO calculation rather than pulling in the
        # full service stack (avoids needing the server to be running).
        affected_canonical_hids: set[int] = set()
        for row in txns:
            alias = (row["symbol"] or "").strip().upper()
            canonical = aliases.get(alias)
            if canonical:
                uid_row = cur.execute(
                    "SELECT user_id FROM holdings WHERE UPPER(symbol)=? AND account_platform=? LIMIT 1",
                    (canonical, row["account_platform"]),
                ).fetchone()
                if uid_row:
                    h2 = cur.execute(
                        "SELECT id FROM holdings WHERE user_id=? AND UPPER(symbol)=? LIMIT 1",
                        (uid_row["user_id"], canonical),
                    ).fetchone()
                    if h2:
                        affected_canonical_hids.add(h2["id"])

        for hid in affected_canonical_hids:
            _recompute_holding_qty(cur, hid)

        conn.commit()
        logger.info(
            "Recomputed qty for %d canonical holding(s): %s",
            len(affected_canonical_hids), sorted(affected_canonical_hids),
        )

        return {"examined": len(txns), "relinked": relinked, "holdings_deleted": deleted}
    finally:
        conn.close()


def _recompute_holding_qty(cur: sqlite3.Cursor, holding_id: int) -> None:
    """Simple net-qty / avg-cost FIFO recompute written directly to the DB row."""
    txns = cur.execute(
        "SELECT txn_type, quantity, price_per_unit FROM investment_transactions "
        "WHERE holding_id=? ORDER BY txn_date, id",
        (holding_id,),
    ).fetchall()

    qty = 0.0
    cost = 0.0
    for t in txns:
        ttype = (t["txn_type"] or "").upper()
        q = float(t["quantity"] or 0)
        p = float(t["price_per_unit"] or 0)
        if ttype in ("BUY", "SIP", "TRANSFER_IN", "DIVIDEND_REINVEST"):
            cost = (cost * qty + p * q) / (qty + q) if (qty + q) > 0 else 0
            qty += q
        elif ttype in ("SELL", "TRANSFER_OUT", "REDEMPTION"):
            qty = max(0.0, qty - q)
            if qty < 1e-9:
                qty = 0.0
                cost = 0.0

    is_active = qty > 1e-9
    cur.execute(
        "UPDATE holdings SET quantity=?, average_cost_per_unit=?, is_active=? WHERE id=?",
        (round(qty, 6), round(cost, 4) if cost else None, 1 if is_active else 0, holding_id),
    )
    h = cur.execute("SELECT symbol, quantity, is_active FROM holdings WHERE id=?", (holding_id,)).fetchone()
    logger.info(
        "  Recomputed holding id=%s symbol=%r → qty=%.4f is_active=%s",
        holding_id, h["symbol"] if h else "?", qty, is_active,
    )


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be changed without modifying the DB",
    )
    args = p.parse_args(argv)

    db = DB_PATH
    logger.info("Using DB: %s", db)
    stats = remediate(db, dry_run=args.dry_run)

    logger.info(
        "Done — examined=%d relinked=%d holdings_deleted=%d%s",
        stats["examined"],
        stats["relinked"],
        stats["holdings_deleted"],
        "  (dry-run, no changes written)" if args.dry_run else "",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
