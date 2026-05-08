"""
Background historical price load for portfolio trend charts after onboarding.

Loads NSE bhav history and MF NAV history into ``prices`` so
``historical_asset_class_values`` can mark replayed positions by month.
Runs in a daemon thread with **batched commits** during NSE history so SQLite
writer locks stay short (HTTP work happens outside long transactions).

See ``scripts/backfill_price_history.py`` for the CLI bulk equivalent.
"""

from __future__ import annotations

import datetime
import logging
import threading
import time
from collections import Counter
from typing import Any

from sqlmodel import Session

from api.database import SQLiteSerializingSession, get_engine
from api.services.historical_portfolio import (
    earliest_user_history_date,
    historical_price_symbol_universe,
)
from api.services.mf_nav_history import (
    fetch_mf_nav_histories_amfi_portal,
    fetch_mf_nav_history_mfapi,
)
from api.services.price_feed import (
    backfill_prices_bulk,
    calendar_start_for_forced_nse_depth,
    latest_bhav_target_date,
    refresh_all_prices,
    upsert_prices,
    weekday_count_inclusive,
)

logger = logging.getLogger(__name__)

_MFAPI_FALLBACK_SLEEP_SEC = 0.35

_status_lock = threading.Lock()
# Per-user backfill progress for GET /api/onboarding/portfolio-price-backfill-status
_status_by_user: dict[str, dict[str, Any]] = {}
_threads: dict[str, threading.Thread] = {}
# Incremented each time we start a background run; workers exit cooperatively when stale.
_generation: dict[str, int] = {}
# Fingerprint of ``historical_price_symbol_universe`` after last **completed** run (skip redundant work).
_last_complete_universe_fp: dict[str, str] = {}


def _universe_fingerprint(session: Session, user_id: str) -> str:
    """Stable string for comparison — skip starting an identical price job after derive."""
    u = historical_price_symbol_universe(session, user_id=user_id)
    keys = ("nse_symbols", "mf_codes", "unsupported_symbols")
    parts = []
    for k in keys:
        v = u.get(k) or []
        parts.append(k + "=" + ",".join(sorted(str(x) for x in v)))
    return "|".join(parts)


def get_price_backfill_status(user_id: str) -> dict[str, Any]:
    """Snapshot of last / current onboarding price import for this user."""
    uid = user_id.strip()
    with _status_lock:
        base = _status_by_user.get(uid)
        if base is None:
            return {
                "status": "idle",
                "symbols_total": 0,
                "symbols_done": 0,
                "days_total": 0,
                "days_done": 0,
                "current_symbol": None,
                "message": None,
                "error": None,
                "started_at": None,
                "finished_at": None,
            }
        return dict(base)


def _utc_now_iso() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat()


def _set_status(uid: str, **kwargs: Any) -> None:
    with _status_lock:
        row = _status_by_user.setdefault(uid, {})
        row.update(kwargs)


def _compute_date_range(session: Session, user_id: str) -> tuple[datetime.date, datetime.date]:
    """Inclusive start/end calendar dates for NSE/MF history fetch."""
    target = latest_bhav_target_date()
    earliest = earliest_user_history_date(session, user_id)
    if earliest is None:
        start = calendar_start_for_forced_nse_depth(
            target,
            depth_calendar_days=365,
            weekend_holiday_buffer_days=14,
        )
    else:
        # Small buffer before first txn so month-end marks exist near the first trade.
        start = earliest - datetime.timedelta(days=14)
    if start > target:
        start = target - datetime.timedelta(days=30)
    return start, target


def run_onboarding_price_backfill_sync(
    user_id: str,
    *,
    expected_generation: int | None = None,
) -> dict[str, Any]:
    """
    Run the full backfill in the current thread (for scripts / tests).

    ``expected_generation`` — when set (background worker), exit early if a newer
    :func:`start_onboarding_price_backfill_background` bumped the generation.

    Returns a summary dict; raises on fatal errors after updating status.
    """
    uid = user_id.strip()
    if not uid:
        raise ValueError("user_id is required")

    def _still_current() -> bool:
        if expected_generation is None:
            return True
        with _status_lock:
            return _generation.get(uid) == expected_generation

    engine = get_engine()
    summary: dict[str, Any] = {
        "nse_symbols_processed": 0,
        "mf_codes_processed": 0,
        "price_rows_refresh": None,
        "unsupported_symbols": [],
    }

    _set_status(
        uid,
        status="running",
        symbols_total=0,
        symbols_done=0,
        days_total=0,
        days_done=0,
        current_symbol=None,
        message="Starting…",
        error=None,
        started_at=_utc_now_iso(),
        finished_at=None,
    )

    try:
        with SQLiteSerializingSession(engine) as session:
            start, target = _compute_date_range(session, uid)
            universe = historical_price_symbol_universe(session, user_id=uid)
            nse_syms = list(universe["nse_symbols"])
            mf_codes = list(universe["mf_codes"])
            unsupported = list(universe.get("unsupported_symbols") or [])
            summary["unsupported_symbols"] = unsupported
            universe_fp = _universe_fingerprint(session, uid)
            summary["universe_fingerprint"] = universe_fp
            if unsupported:
                logger.warning(
                    "Onboarding price backfill: skipping unsupported symbols %s",
                    unsupported,
                )

            weekday_total = weekday_count_inclusive(start, target)
            mf_step = 1 if mf_codes else 0
            progress_total = weekday_total + mf_step
            _set_status(
                uid,
                symbols_total=progress_total,
                symbols_done=0,
                days_total=weekday_total,
                days_done=0,
                message=f"Loading prices from {start.isoformat()} to {target.isoformat()}…",
            )

        # NSE: one bhavcopy per **session** — extract all symbols (not one download per ticker).
        if nse_syms:

            def _on_nse_day(done: int, total: int, sess_date: datetime.date) -> None:
                _set_status(
                    uid,
                    days_total=total,
                    days_done=done,
                    symbols_total=progress_total,
                    symbols_done=done,
                    current_symbol=sess_date.isoformat(),
                    message=f"NSE sessions {done}/{total} ({sess_date.isoformat()})…",
                )

            with SQLiteSerializingSession(engine) as session:
                res = backfill_prices_bulk(
                    session,
                    nse_syms,
                    start,
                    target,
                    progress_callback=_on_nse_day,
                    still_current=_still_current,
                )
            summary["nse_bulk_backfill"] = res
            summary["nse_symbols_processed"] = len(nse_syms)
            if res.get("status") == "superseded":
                logger.info(
                    "Onboarding price backfill superseded during NSE (user=%s gen=%s)",
                    uid,
                    expected_generation,
                )
                summary["superseded"] = True
                return summary
            logger.info(
                "Onboarding price backfill NSE bulk user=%s -> %s",
                uid,
                res,
            )
            _set_status(
                uid,
                symbols_done=weekday_total,
                days_done=weekday_total,
                current_symbol=None,
                message="NSE history loaded…",
            )

        # MF: AMFI portal (+ mfapi fallback per scheme), then one commit.
        if mf_codes:
            if not _still_current():
                logger.info(
                    "Onboarding price backfill superseded before MF (user=%s gen=%s)",
                    uid,
                    expected_generation,
                )
                summary["superseded"] = True
                return summary

            _set_status(
                uid,
                current_symbol="MF_NAV",
                message="Loading mutual fund history…",
                symbols_total=progress_total,
                symbols_done=weekday_total if nse_syms else 0,
                days_total=weekday_total,
                days_done=weekday_total if nse_syms else 0,
            )
            with SQLiteSerializingSession(engine) as session:
                mf_rows = fetch_mf_nav_histories_amfi_portal(mf_codes, start, target)
                got = Counter(r.symbol for r in mf_rows)
                for j, code in enumerate(mf_codes):
                    if not _still_current():
                        logger.info(
                            "Onboarding price backfill superseded during MF (user=%s)",
                            uid,
                        )
                        summary["superseded"] = True
                        return summary
                    if got[code] == 0:
                        logger.warning(
                            "MF scheme %s: AMFI portal empty; trying mfapi.in",
                            code,
                        )
                        extra = fetch_mf_nav_history_mfapi(code, start, target)
                        mf_rows.extend(extra)
                        if j < len(mf_codes) - 1:
                            time.sleep(_MFAPI_FALLBACK_SLEEP_SEC)
                touched = upsert_prices(session, mf_rows) if mf_rows else 0
                _flush_and_commit = getattr(session, "flush_and_commit", None)
                if _flush_and_commit is not None:
                    _flush_and_commit()
                else:
                    session.commit()
                logger.info(
                    "Onboarding price backfill MF user=%s codes=%s rows_touched=%s",
                    uid,
                    len(mf_codes),
                    touched,
                )
            summary["mf_codes_processed"] = len(mf_codes)
            _set_status(
                uid,
                symbols_total=progress_total,
                symbols_done=progress_total,
                days_total=weekday_total,
                days_done=weekday_total,
                current_symbol=None,
                message="Mutual fund history loaded…",
            )

        if not _still_current():
            summary["superseded"] = True
            return summary

        # Refresh marks on holdings so live totals match imported prices.
        with SQLiteSerializingSession(engine) as session:
            refreshed = refresh_all_prices(session, user_id=uid)
            session.commit()
            summary["price_rows_refresh"] = refreshed

        if not _still_current():
            summary["superseded"] = True
            return summary

        with _status_lock:
            _last_complete_universe_fp[uid] = universe_fp

        _set_status(
            uid,
            status="complete",
            symbols_done=_status_by_user.get(uid, {}).get("symbols_total", 0),
            days_done=_status_by_user.get(uid, {}).get("days_total", 0),
            current_symbol=None,
            message="Done.",
            finished_at=_utc_now_iso(),
            error=None,
        )
        return summary

    except Exception as e:
        logger.exception("Onboarding price backfill failed for user=%s", uid)
        _set_status(
            uid,
            status="error",
            error=str(e),
            message=None,
            finished_at=_utc_now_iso(),
        )
        raise


def _worker(user_id: str, generation: int) -> None:
    try:
        run_onboarding_price_backfill_sync(user_id, expected_generation=generation)
    finally:
        with _status_lock:
            cur = _threads.get(user_id)
            if cur is threading.current_thread():
                _threads.pop(user_id, None)


def start_onboarding_price_backfill_background(
    user_id: str,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Start a daemon thread to load historical prices for ``user_id``.

    A **new** call while a job is running bumps the generation so the old worker
    exits cooperatively; this thread then runs with an up-to-date symbol universe
    (e.g. after a statement upload).

    When ``force`` is False and the last run **completed** with the same symbol-universe
    fingerprint as now, returns ``started: False`` with ``reason: universe_unchanged``
    (avoids redundant NSE/MF traffic). A running job or incomplete/error state always
    starts (or restarts) work.

    Returns ``{"started": True}`` or ``{"started": False, "reason": "..."}``.
    """
    uid = user_id.strip()
    if not uid:
        return {"started": False, "reason": "empty_user"}

    engine = get_engine()
    with SQLiteSerializingSession(engine) as session:
        fp_now = _universe_fingerprint(session, uid)

    with _status_lock:
        st = dict(_status_by_user.get(uid, {}))
        prev_status = str(st.get("status") or "idle")
        last_fp = _last_complete_universe_fp.get(uid)

    if not force:
        if prev_status == "running":
            pass  # always restart / supersede — fingerprint may match but job incomplete
        elif prev_status == "complete" and last_fp == fp_now:
            return {"started": False, "reason": "universe_unchanged"}
        # idle / error / cancelled: proceed

    with _status_lock:
        _generation[uid] = _generation.get(uid, 0) + 1
        gen = _generation[uid]

    th = threading.Thread(
        target=_worker,
        args=(uid, gen),
        daemon=True,
        name=f"arth-price-backfill-{uid}",
    )
    with _status_lock:
        _threads[uid] = th
    th.start()
    return {"started": True, "generation": gen}
