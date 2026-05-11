#!/usr/bin/env python3
"""
Rebuild **demo user** equity + mutual-fund ``investment_transactions`` and holding
marks from whatever is already in the ``prices`` table (NSE bhav + AMFI NAV).

Typical local workflow (golden demo DB)::

    python3 scripts/generate_demo_seed.py

    # Optional: drop synthetic calendar fills so NSE/MF rows are the only source.
    sqlite3 data/arth_demo_seed.db \\
      "DELETE FROM prices WHERE source = 'demo_seed' AND symbol IN (
         'HDFCBANK','SBIN','TCS','INFY','RELIANCE','ITC','ASIANPAINT','TATAMOTORS',
         '122639','118551');"

    ARTH_DB_PATH=data/arth_demo_seed.db python3 scripts/backfill_price_history.py \\
        --user-id demo --days 2000

    ARTH_DB_PATH=data/arth_demo_seed.db python3 scripts/materialize_demo_market_from_prices.py

``--days`` should cover ``demo_portfolio_plan.DEMO_HISTORY_LOOKBACK_DAYS`` (about
five years) so every SIP date can resolve a close on or before that day.
"""

from __future__ import annotations

import argparse
import datetime
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=os.environ.get("ARTH_DB_PATH", str(REPO / "data" / "arth_demo_seed.db")),
        help="SQLite file (sets ARTH_DB_PATH for this process). Default: env or data/arth_demo_seed.db",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned row counts only; no deletes or inserts.",
    )
    args = parser.parse_args()

    db_path = Path(args.db).expanduser().resolve()
    os.environ["ARTH_DB_PATH"] = str(db_path)

    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    scripts_dir = REPO / "scripts"
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))

    import demo_portfolio_plan as dpp  # noqa: WPS433 (runtime path)
    from sqlalchemy import delete, func
    from sqlmodel import Session, col, select

    from api.database import SQLiteSerializingSession, get_engine
    from api.models import Holding, InvestmentTransaction, Price
    from pipeline.models import AssetClass

    today = datetime.date.today()
    anchor = dpp.demo_cost_anchor_date(today)
    sip_dates = dpp.monthly_investment_dates(
        dpp.demo_history_start(today), today, day_of_month=dpp.DEMO_MONTHLY_SIP_DOM
    )

    def close_on_or_before(session: Session, symbol: str, as_of: datetime.date) -> float | None:
        row = session.exec(
            select(Price.close_price)
            .where(Price.symbol == symbol, Price.date <= as_of)
            .order_by(col(Price.date).desc())
            .limit(1)
        ).first()
        return float(row) if row is not None else None

    uid = dpp.DEMO_USER_ID
    with SQLiteSerializingSession(get_engine()) as session:
        market_ids = list(
            session.exec(
                select(Holding.id).where(
                    Holding.user_id == uid,
                    Holding.asset_class.in_(
                        (AssetClass.EQUITY.value, AssetClass.MUTUAL_FUND.value)
                    ),
                )
            ).all()
        )
        market_ids = [int(x) for x in market_ids if x is not None]
        if not market_ids:
            print("No equity/MF holdings for demo user — nothing to do.")
            return 1

        n_delete = int(
            session.exec(
                select(func.count())
                .select_from(InvestmentTransaction)
                .where(InvestmentTransaction.holding_id.in_(tuple(market_ids)))
            ).one()
        )
        print(f"Replacing {n_delete} market investment_transactions across {len(market_ids)} holdings.")

        if args.dry_run:
            return 0

        session.execute(delete(InvestmentTransaction).where(InvestmentTransaction.holding_id.in_(market_ids)))
        session.commit()

        by_key: dict[tuple[str, str], int] = {}
        for spec in dpp.DEMO_EQUITY_SPECS:
            sym = str(spec["symbol"])
            hid = session.exec(
                select(Holding.id).where(
                    Holding.user_id == uid,
                    Holding.symbol == sym,
                    Holding.asset_class == AssetClass.EQUITY.value,
                )
            ).first()
            if hid is not None:
                by_key[("eq", sym)] = int(hid)
        for spec in dpp.DEMO_MF_SPECS:
            sym = str(spec["symbol"])
            hid = session.exec(
                select(Holding.id).where(
                    Holding.user_id == uid,
                    Holding.symbol == sym,
                    Holding.asset_class == AssetClass.MUTUAL_FUND.value,
                )
            ).first()
            if hid is not None:
                by_key[("mf", sym)] = int(hid)

        inv_rows: list[InvestmentTransaction] = []
        holding_updates: dict[int, tuple[float, float, float, float]] = {}

        for spec in dpp.DEMO_EQUITY_SPECS:
            sym = str(spec["symbol"])
            hid = by_key.get(("eq", sym))
            if hid is None:
                continue
            plan_rows, qty, px_a, px_t = dpp.build_market_ledger_plan(
                spec=spec,
                holding_id=hid,
                sip_dates=sip_dates,
                close_on_or_before=lambda s, d, _s=session: close_on_or_before(_s, s, d),
                anchor_date=anchor,
                today=today,
            )
            for pr in plan_rows:
                inv_rows.append(InvestmentTransaction(**pr))
            if px_a is not None and px_t is not None and qty > 0:
                holding_updates[hid] = (qty, px_a, px_t, round(qty * px_t, 2))

        for spec in dpp.DEMO_MF_SPECS:
            sym = str(spec["symbol"])
            hid = by_key.get(("mf", sym))
            if hid is None:
                continue
            plan_rows, qty, px_a, px_t = dpp.build_market_ledger_plan(
                spec=spec,
                holding_id=hid,
                sip_dates=sip_dates,
                close_on_or_before=lambda s, d, _s=session: close_on_or_before(_s, s, d),
                anchor_date=anchor,
                today=today,
            )
            for pr in plan_rows:
                inv_rows.append(InvestmentTransaction(**pr))
            if px_a is not None and px_t is not None and qty > 0:
                holding_updates[hid] = (qty, px_a, px_t, round(qty * px_t, 2))

        for ir in inv_rows:
            session.add(ir)
        session.commit()

        for hid, (qty, px_a, px_t, cur) in holding_updates.items():
            h = session.get(Holding, hid)
            if h is None:
                continue
            h.quantity = qty
            h.average_cost_per_unit = px_a
            h.current_price_per_unit = px_t
            h.current_value = cur
            session.add(h)
        session.commit()

        print(f"Inserted {len(inv_rows)} market investment rows; updated {len(holding_updates)} holdings.")

        for sym in dpp.demo_market_price_symbols():
            row = session.exec(
                select(func.min(Price.date), func.max(Price.date), func.count())
                .where(Price.symbol == sym)
            ).one()
            mn, mx, n = row[0], row[1], int(row[2] or 0)
            print(f"  prices[{sym}]: n={n} min={mn} max={mx}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
