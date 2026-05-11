#!/usr/bin/env python3
"""
Load roughly one calendar year of rows into ``prices`` for the historical portfolio symbol universe:

* **NSE-listed** sleeves (equity, ESOP, SGB, Indian gold ETF tickers) — official bhavcopy
  **one session file per trading day** (each file lists the whole exchange). We load that
  map once per weekday and upsert every requested symbol — **not** once per symbol per day.
* **Open-ended mutual funds** — historical NAV from the **AMFI portal** NAV history report
  (official), with **mfapi.in** only as a per-scheme fallback if a scheme has no rows.
* Includes **historically traded** symbols from linked ``investment_transactions`` so
  fully sold positions can still be valued in old months. ``STOONE`` is excluded.

**Database:** Set ``APP_ENV`` before running — same as the API (``test`` → ``data/arth_test.db``,
default ``prod`` → ``data/arth_main.db``).  See ``scripts/README.md`` for prerequisites and runbook.

Run from repo root::

    APP_ENV=test python3 scripts/backfill_price_history.py --days 365
    APP_ENV=test python3 scripts/backfill_price_history.py --days 365 --mf-only
    python3 scripts/backfill_price_history.py --days 365 --dry-run

NSE progress logs (with ETA) emit every ``--progress-every`` trading sessions (default: 25).
"""

from __future__ import annotations

import argparse
import datetime
import logging
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_price_history")

# Space out mfapi.in fallback calls slightly (third-party; be polite).
_MFAPI_FALLBACK_SLEEP_SEC = 0.35


def _format_eta_seconds(eta_sec: float) -> str:
    if eta_sec <= 0 or eta_sec == float("inf"):
        return "ETA —"
    if eta_sec < 75:
        return f"ETA ~{eta_sec:.0f}s"
    if eta_sec < 3600:
        return f"ETA ~{eta_sec / 60:.1f}m"
    return f"ETA ~{eta_sec / 3600:.1f}h"


def _weekdays_inclusive(start: datetime.date, end: datetime.date) -> int:
    """Count Mon–Fri days in ``[start, end]`` (NSE bhav attempts one file per such day)."""
    n = 0
    d = start
    while d <= end:
        if d.weekday() < 5:
            n += 1
        d += datetime.timedelta(days=1)
    return n


def _first_weekday_on_or_after(d: datetime.date) -> datetime.date:
    out = d
    while out.weekday() >= 5:
        out += datetime.timedelta(days=1)
    return out


def _filtered_nse_symbols(symbols: list[str], start_symbol: str | None) -> list[str]:
    if not start_symbol:
        return symbols
    want = start_symbol.strip().upper()
    try:
        idx = symbols.index(want)
    except ValueError:
        logger.warning("--start-symbol=%s not found in NSE symbol list; running full list", want)
        return symbols
    return symbols[idx:]


def _chunk_symbols(symbols: list[str], chunk_count: int, chunk_index: int) -> list[str]:
    if chunk_count <= 1:
        return symbols
    total = len(symbols)
    if total == 0:
        return []
    base = total // chunk_count
    extra = total % chunk_count
    if chunk_index < extra:
        start = chunk_index * (base + 1)
        end = start + base + 1
    else:
        start = extra * (base + 1) + (chunk_index - extra) * base
        end = start + base
    return symbols[start:end]


def _already_covered_symbols(
    session,
    symbols: list[str],
    *,
    start: datetime.date,
    target: datetime.date,
) -> set[str]:
    from api.models import Price
    from sqlalchemy import func
    from sqlmodel import col, select

    covered: set[str] = set()
    effective_start = _first_weekday_on_or_after(start)
    for sym in symbols:
        mn, mx = session.exec(
            select(func.min(Price.date), func.max(Price.date)).where(Price.symbol == sym)
        ).one()
        if mn is not None and mx is not None and mn <= effective_start and mx >= target:
            covered.add(sym)
    return covered


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill prices (NSE bhav + MF AMFI portal history) for current portfolio symbols.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Approximate calendar depth to cover (~1y of trading sessions); default 365.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print symbol lists, date range, and estimated weekday count; no HTTP or DB writes.",
    )
    parser.add_argument(
        "--user-id",
        default=None,
        help="If set, only holdings for this user_id are considered.",
    )
    parser.add_argument(
        "--buffer-days",
        type=int,
        default=14,
        help="Extra calendar days before --days window for NSE weekends/holidays (default 14).",
    )
    parser.add_argument(
        "--mf-only",
        action="store_true",
        help="Skip NSE bhav backfill; only load MF history (AMFI portal + mfapi fallback).",
    )
    parser.add_argument(
        "--start-symbol",
        default=None,
        help="Resume NSE backfill from this canonical symbol (inclusive), e.g. BAJAJFINSV.",
    )
    parser.add_argument(
        "--chunk-count",
        type=int,
        default=1,
        help="Split NSE symbol list into this many contiguous chunks (default 1).",
    )
    parser.add_argument(
        "--chunk-index",
        type=int,
        default=0,
        help="0-based chunk index to run when using --chunk-count.",
    )
    parser.add_argument(
        "--skip-completed",
        action="store_true",
        help="Skip NSE symbols that already have prices covering the full requested range.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=25,
        metavar="N",
        help="Log NSE progress (with ETA) every N trading sessions (default: 25). Use 1 for noisy output.",
    )
    args = parser.parse_args()
    if args.chunk_count < 1:
        parser.error("--chunk-count must be >= 1")
    if args.chunk_index < 0 or args.chunk_index >= args.chunk_count:
        parser.error("--chunk-index must be between 0 and chunk-count-1")
    if args.progress_every < 1:
        parser.error("--progress-every must be >= 1")

    # Imported after sys.path so `api` resolves; APP_ENV is read from the environment when
    # pipeline.config loads (set it in the shell before invoking this script).
    from sqlalchemy import func
    from sqlmodel import Session, col, select

    from api.database import get_engine
    from collections import Counter

    from api.services.historical_portfolio import historical_price_symbol_universe
    from api.services.mf_nav_history import (
        fetch_mf_nav_histories_amfi_portal,
        fetch_mf_nav_history_mfapi,
    )
    from api.models import Price
    from api.services.price_feed import (
        bhav_cached_csv_path,
        calendar_start_for_forced_nse_depth,
        canonical_nse_symbol,
        latest_bhav_target_date,
        load_nse_equity_bhav_map_cached_first,
        upsert_prices,
    )
    from pipeline.config import APP_ENV, DB_PATH

    engine = get_engine()
    target = latest_bhav_target_date()
    start = calendar_start_for_forced_nse_depth(
        target,
        depth_calendar_days=args.days,
        weekend_holiday_buffer_days=args.buffer_days,
    )

    with Session(engine) as session:
        uid = str(args.user_id).strip() if args.user_id is not None else "sashank"
        universe = historical_price_symbol_universe(session, user_id=uid)
        nse_syms = universe["nse_symbols"]
        mf_codes = universe["mf_codes"]
        unsupported_syms = universe["unsupported_symbols"]
        if args.skip_completed:
            covered = _already_covered_symbols(session, nse_syms, start=start, target=target)
            if covered:
                logger.info("Skipping already covered NSE symbols (%d): %s", len(covered), ", ".join(sorted(covered)))
            nse_syms = [sym for sym in nse_syms if sym not in covered]
    nse_syms = _filtered_nse_symbols(nse_syms, args.start_symbol)
    nse_syms = _chunk_symbols(nse_syms, args.chunk_count, args.chunk_index)
    if args.chunk_count > 1 and args.chunk_index != 0 and not args.mf_only:
        mf_codes = []

    norm_nse_syms = sorted({canonical_nse_symbol(s) for s in nse_syms}) if nse_syms else []

    logger.info("APP_ENV=%s DB_PATH=%s", APP_ENV, DB_PATH)
    if args.mf_only:
        logger.info("Mode: --mf-only (NSE bhav skipped)")
    logger.info("NSE latest session date (weekday anchor): %s", target)
    logger.info("Backfill inclusive range: %s .. %s", start, target)
    if not args.mf_only:
        n_sessions = _weekdays_inclusive(start, target)
        logger.info(
            "NSE: up to %d trading sessions (one bhav map load per session for all symbols)",
            n_sessions,
        )
    logger.info(
        "NSE symbols to extract (%d): %s",
        len(norm_nse_syms),
        ", ".join(norm_nse_syms) or "(none)",
    )
    if args.chunk_count > 1:
        logger.info("Running NSE chunk %d/%d", args.chunk_index + 1, args.chunk_count)
    logger.info("MF scheme codes (%d): %s", len(mf_codes), ", ".join(mf_codes) or "(none)")
    if unsupported_syms:
        logger.warning(
            "Symbols with no deep backfill path in this script (%d): %s",
            len(unsupported_syms),
            ", ".join(unsupported_syms),
        )

    if args.dry_run:
        return 0

    with Session(engine) as session:
        if not args.mf_only and norm_nse_syms:
            total_weekdays = _weekdays_inclusive(start, target)
            per_sym_hits: dict[str, int] = {s: 0 for s in norm_nse_syms}
            per_sym_misses: dict[str, int] = {s: 0 for s in norm_nse_syms}
            empty_sessions = 0
            processed = 0
            buffered_rows: list[Price] = []
            t_nse0 = time.monotonic()
            n_cache_days = 0
            n_network_days = 0
            d = start

            def _nse_progress_note(cur_d: datetime.date, *, note: str, day_prices: int = 0) -> None:
                pct = (100.0 * processed / total_weekdays) if total_weekdays > 0 else 100.0
                elapsed = max(time.monotonic() - t_nse0, 1e-6)
                rate = processed / elapsed
                remaining = max(0, total_weekdays - processed)
                eta_sec = remaining / rate if rate > 0 else float("inf")
                logger.info(
                    "NSE progress %d/%d sessions (%.1f%%) date=%s %s | "
                    "cache_days=%d net_days=%d empty_maps=%d day_prices=%d | %s (%.2f sessions/s)",
                    processed,
                    total_weekdays,
                    pct,
                    cur_d.isoformat(),
                    note,
                    n_cache_days,
                    n_network_days,
                    empty_sessions,
                    day_prices,
                    _format_eta_seconds(eta_sec),
                    processed / elapsed,
                )

            while d <= target:
                if d.weekday() >= 5:
                    d += datetime.timedelta(days=1)
                    continue
                processed += 1
                full_map = load_nse_equity_bhav_map_cached_first(d)
                if not full_map:
                    empty_sessions += 1
                    time.sleep(0.05)
                    if (
                        processed == 1
                        or processed % args.progress_every == 0
                        or d == target
                    ):
                        _nse_progress_note(d, note="no bhav map for this date", day_prices=0)
                    d += datetime.timedelta(days=1)
                    continue

                day_prices = 0
                for sym in norm_nse_syms:
                    close = full_map.get(sym)
                    if close is not None:
                        buffered_rows.append(
                            Price(symbol=sym, date=d, close_price=float(close), source="nse")
                        )
                        per_sym_hits[sym] += 1
                        day_prices += 1
                    else:
                        per_sym_misses[sym] += 1

                if bhav_cached_csv_path(d) is None:
                    n_network_days += 1
                    time.sleep(0.35)
                else:
                    n_cache_days += 1
                    time.sleep(0.0)

                if buffered_rows and (len(buffered_rows) >= 200 or d == target):
                    upsert_prices(session, buffered_rows)
                    session.commit()
                    buffered_rows.clear()

                if (
                    processed == 1
                    or processed % args.progress_every == 0
                    or d == target
                ):
                    _nse_progress_note(d, note="bhav ok", day_prices=day_prices)
                d += datetime.timedelta(days=1)

            if buffered_rows:
                upsert_prices(session, buffered_rows)
                session.commit()

            for sym in norm_nse_syms:
                logger.info(
                    "NSE %s -> hits=%d misses=%d",
                    sym,
                    per_sym_hits[sym],
                    per_sym_misses[sym],
                )
            logger.info(
                "NSE pass done: %d trading days walked, %d sessions with no bhav map",
                processed,
                empty_sessions,
            )

        elif not args.mf_only and not norm_nse_syms:
            logger.info("NSE: no symbols to backfill (empty universe or all skipped as complete).")

        if args.mf_only and not mf_codes:
            logger.warning("--mf-only but no MF scheme codes on holdings — nothing to write")

        if mf_codes:
            logger.info(
                "MF phase — AMFI portal: fetching NAV history for %d scheme(s), %s .. %s …",
                len(mf_codes),
                start,
                target,
            )
            t_mf0 = time.monotonic()
            mf_rows = fetch_mf_nav_histories_amfi_portal(mf_codes, start, target)
            logger.info(
                "MF phase — AMFI portal done in %.1fs (%d raw NAV rows).",
                time.monotonic() - t_mf0,
                len(mf_rows),
            )
            got = Counter(r.symbol for r in mf_rows)
            for j, code in enumerate(mf_codes):
                if got[code] == 0:
                    logger.warning(
                        "MF [%d/%d] scheme %s: no AMFI portal rows; trying mfapi.in",
                        j + 1,
                        len(mf_codes),
                        code,
                    )
                    extra = fetch_mf_nav_history_mfapi(code, start, target)
                    mf_rows.extend(extra)
                    logger.info(
                        "MF [%d/%d] scheme %s: mfapi.in -> %d row(s)",
                        j + 1,
                        len(mf_codes),
                        code,
                        len(extra),
                    )
                    if j < len(mf_codes) - 1:
                        time.sleep(_MFAPI_FALLBACK_SLEEP_SEC)
                else:
                    logger.info(
                        "MF [%d/%d] scheme %s: AMFI portal -> %d row(s)",
                        j + 1,
                        len(mf_codes),
                        code,
                        got[code],
                    )
            touched = upsert_prices(session, mf_rows) if mf_rows else 0
            logger.info(
                "MF phase — SQLite upsert finished: %d row(s) touched from %d raw NAV rows.",
                touched,
                len(mf_rows),
            )

        session.commit()

    logger.info("Committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
