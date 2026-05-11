"""
Shared knobs for ``generate_demo_seed.py`` + ``materialize_demo_market_from_prices.py``.

The public demo can ship **synthetic** daily prices (offline / Docker), or you can
rebuild the equity/MF ledger from **real** ``prices`` rows after::

    ARTH_DB_PATH=data/arth_demo_seed.db python3 scripts/backfill_price_history.py \\
        --user-id demo --days 2000

Monthly SIP amounts here are INR notionals; units bought = amount / close on the
SIP date (fractional units allowed), so the portfolio trend follows real marks once
the cache is populated.
"""

from __future__ import annotations

import calendar
import datetime
from collections.abc import Callable, Iterable
from typing import Any

from pipeline.models import InvestmentTxnType

DEMO_USER_ID = "demo"

# ~5 calendar years of history (portfolio trend + earliest txn date).
DEMO_HISTORY_LOOKBACK_DAYS = int(365 * 5 + 30)

# "Book cost" anchor: average_cost_per_unit uses close on or before this day.
DEMO_COST_ANCHOR_DAYS_AGO = 420

# SIP executes on this calendar day-of-month (clamped to month-end). If the
# exchange has no row on that **exact** calendar day, callers should use the
# latest close on or before the SIP date (same rule as live Arth).
DEMO_MONTHLY_SIP_DOM = 12


def demo_history_start(today: datetime.date | None = None) -> datetime.date:
    base = today or datetime.date.today()
    return base - datetime.timedelta(days=DEMO_HISTORY_LOOKBACK_DAYS)


def demo_cost_anchor_date(today: datetime.date | None = None) -> datetime.date:
    base = today or datetime.date.today()
    return base - datetime.timedelta(days=DEMO_COST_ANCHOR_DAYS_AGO)


def monthly_investment_dates(
    start: datetime.date,
    end: datetime.date,
    *,
    day_of_month: int = DEMO_MONTHLY_SIP_DOM,
) -> list[datetime.date]:
    """Each month: first ``day_of_month`` on or after ``start``, through ``end``."""
    out: list[datetime.date] = []
    y, m = start.year, start.month
    while True:
        last = calendar.monthrange(y, m)[1]
        dom = min(int(day_of_month), last)
        d = datetime.date(y, m, dom)
        if d <= end and d >= start:
            out.append(d)
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
        if datetime.date(y, m, 1) > end:
            break
    return out


# Equities: ``monthly_sip_inr`` + optional ``initial_lump_inr`` on the first SIP date.
# HDFC Bank + SBI are intentionally overweight vs the rest for a bank-heavy demo.
DEMO_EQUITY_SPECS: list[dict[str, Any]] = [
    {
        "symbol": "HDFCBANK",
        "name": "HDFC Bank Ltd",
        "sector": "BANKS",
        "market_cap_class": "LARGE_CAP",
        "platform": "HDFC Securities",
        "monthly_sip_inr": 28_000.0,
        "initial_lump_inr": 220_000.0,
    },
    {
        "symbol": "SBIN",
        "name": "State Bank of India",
        "sector": "BANKS",
        "market_cap_class": "LARGE_CAP",
        "platform": "SBI Securities",
        "monthly_sip_inr": 22_000.0,
        "initial_lump_inr": 140_000.0,
    },
    {
        "symbol": "TCS",
        "name": "Tata Consultancy Services",
        "sector": "COMPUTERS - SOFTWARE",
        "market_cap_class": "LARGE_CAP",
        "platform": "ICICI Direct",
        "monthly_sip_inr": 12_000.0,
        "initial_lump_inr": 80_000.0,
    },
    {
        "symbol": "INFY",
        "name": "Infosys Ltd",
        "sector": "COMPUTERS - SOFTWARE",
        "market_cap_class": "LARGE_CAP",
        "platform": "ICICI Direct",
        "monthly_sip_inr": 10_000.0,
        "initial_lump_inr": 60_000.0,
    },
    {
        "symbol": "RELIANCE",
        "name": "Reliance Industries Ltd",
        "sector": "PETROLEUM PRODUCTS",
        "market_cap_class": "LARGE_CAP",
        "platform": "Zerodha",
        "monthly_sip_inr": 9_000.0,
        "initial_lump_inr": 45_000.0,
    },
    {
        "symbol": "ITC",
        "name": "ITC Ltd",
        "sector": "CONSUMER GOODS",
        "market_cap_class": "LARGE_CAP",
        "platform": "ICICI Direct",
        "monthly_sip_inr": 8_000.0,
        "initial_lump_inr": 40_000.0,
    },
    {
        "symbol": "ASIANPAINT",
        "name": "Asian Paints Ltd",
        "sector": "PAINTS",
        "market_cap_class": "LARGE_CAP",
        "platform": "ICICI Direct",
        "monthly_sip_inr": 7_500.0,
        "initial_lump_inr": 35_000.0,
    },
    {
        "symbol": "TATAMOTORS",
        "name": "Tata Motors Ltd",
        "sector": "AUTOMOBILES - 4 WHEELERS",
        "market_cap_class": "LARGE_CAP",
        "platform": "Groww",
        "monthly_sip_inr": 7_500.0,
        "initial_lump_inr": 35_000.0,
    },
]

DEMO_MF_SPECS: list[dict[str, Any]] = [
    {
        "symbol": "122639",
        "name": "Parag Parikh Flexi Cap Fund - Direct Growth",
        "platform": "Zerodha Coin",
        "fund_category": "Equity Scheme - Flexi Cap Fund",
        "fund_house": "PPFAS Mutual Fund",
        "monthly_sip_inr": 25_000.0,
        "initial_lump_inr": 120_000.0,
    },
    {
        "symbol": "118551",
        "name": "HDFC Top 100 Fund - Direct Growth",
        "platform": "HDFC Bank",
        "fund_category": "Equity Scheme - Large Cap Fund",
        "fund_house": "HDFC Mutual Fund",
        "monthly_sip_inr": 15_000.0,
        "initial_lump_inr": 75_000.0,
    },
]


def demo_market_price_symbols() -> list[str]:
    eq = [str(s["symbol"]) for s in DEMO_EQUITY_SPECS]
    mf = [str(s["symbol"]) for s in DEMO_MF_SPECS]
    return sorted(set(eq + mf))


def _row(
    *,
    txn_date: datetime.date,
    symbol: str | None,
    txn_type: str,
    quantity: float,
    price_per_unit: float,
    total_amount: float,
    account_platform: str,
    holding_id: int,
) -> dict[str, Any]:
    return {
        "txn_date": txn_date,
        "symbol": symbol,
        "txn_type": txn_type,
        "quantity": quantity,
        "price_per_unit": price_per_unit,
        "total_amount": total_amount,
        "account_platform": account_platform,
        "holding_id": holding_id,
        "is_reviewed": True,
        "source_type": "statement",
    }


def build_market_ledger_plan(
    *,
    spec: dict[str, Any],
    holding_id: int,
    sip_dates: Iterable[datetime.date],
    close_on_or_before: Callable[[str, datetime.date], float | None],
    anchor_date: datetime.date,
    today: datetime.date,
) -> tuple[list[dict[str, Any]], float, float | None, float | None]:
    """
    Build BUY (optional lump) + monthly SIP dicts; return rows and final qty.

    ``close_on_or_before`` must implement "latest close <= date" semantics (NSE
    holidays, SIP on Sunday, etc.).
    """
    sym = str(spec["symbol"])
    platform = str(spec["platform"])
    sip_inr = float(spec["monthly_sip_inr"])
    lump_inr = float(spec.get("initial_lump_inr") or 0.0)

    rows: list[dict[str, Any]] = []
    qty_total = 0.0

    for i, d in enumerate(sip_dates):
        px = close_on_or_before(sym, d)
        if px is None or px <= 0:
            continue
        if i == 0 and lump_inr > 0:
            q = lump_inr / px
            qty_total += q
            rows.append(
                _row(
                    txn_date=d,
                    symbol=sym,
                    txn_type=InvestmentTxnType.BUY.value,
                    quantity=round(q, 6),
                    price_per_unit=round(px, 4),
                    total_amount=round(lump_inr, 2),
                    account_platform=platform,
                    holding_id=holding_id,
                )
            )
        q_sip = sip_inr / px
        qty_total += q_sip
        rows.append(
            _row(
                txn_date=d,
                symbol=sym,
                txn_type=InvestmentTxnType.SIP.value,
                quantity=round(q_sip, 6),
                price_per_unit=round(px, 4),
                total_amount=round(sip_inr, 2),
                account_platform=platform,
                holding_id=holding_id,
            )
        )

    px_anchor = close_on_or_before(sym, anchor_date)
    px_today = close_on_or_before(sym, today)
    return rows, round(qty_total, 6), px_anchor, px_today
