"""
Resolve Indian equity ISIN → NSE ``TckrSymb`` using a **local** consolidated bhav map.

The map is built from cached NSE equity bhav CSVs under ``data/.nse_cache`` (see
:mod:`pipeline.bhav_isin_map` and ``pipeline/consolidate_bhav_cache.py``). Each
successful price refresh merges the session’s bhav file so the map stays current
without live NSE calls during parsing.

Optional ``isin_to_nse`` rows in ``data/icici_nse_symbol_overrides.json`` still apply
as a fallback after the consolidated map (delisted / edge cases).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# In-process cache of the consolidated JSON (invalidated after map updates).
_map_cache: dict[str, dict[str, Any]] | None = None

# Curated blocklist — fraud / forced delistings / SEBI suspensions we never want to ingest.
# Review ``data/.nse_cache/delisted_isin_candidates.json`` periodically for additions.
IGNORED_ISINS: frozenset[str] = frozenset(
    {
        "INE148I01020",  # STOONE — SEBI trading halt / delisted equity
        "INE034H01016",  # SORILINFRA — user-requested exclude (delisted / illiquid)
    }
)

# Broker short codes / legacy rows without ISIN in metadata — skip by resolved symbol.
IGNORED_SYMBOLS: frozenset[str] = frozenset(
    {"STOONE", "INDWHO", "IBULLSLTD", "SORILINFRA"},
)


def is_curated_ignored_security(*, symbol: str | None, isin: str | None = None) -> bool:
    """True when ``symbol`` / ``isin`` match the pipeline blocklist.

    After aggregation, a blocked ISIN may appear **only** in ``symbol`` (raw ISIN string)
    while ``metadata["isin"]`` is empty — callers must pass both columns when available.
    """
    sym = (symbol or "").strip().upper()
    iso = (isin or "").strip().upper()
    if sym in IGNORED_SYMBOLS:
        return True
    if iso in IGNORED_ISINS:
        return True
    if sym in IGNORED_ISINS:
        return True
    return False


def is_curated_ignored_holding_row(obj: object) -> bool:
    """True for a ``Holding``-shaped ORM row on the blocklist.

    Uses ``getattr`` so we never touch ``.isin`` if the model or SQLite row predates
    that column — Pydantic/SQLModel would otherwise raise on missing attributes.
    """
    return is_curated_ignored_security(
        symbol=getattr(obj, "symbol", None),
        isin=getattr(obj, "isin", None),
    )


def invalidate_bhav_isin_cache() -> None:
    """Clear the in-process consolidated map (call after updating the JSON file)."""
    global _map_cache
    _map_cache = None


def _load_map() -> dict[str, dict[str, Any]]:
    global _map_cache
    if _map_cache is not None:
        return _map_cache
    from pipeline.bhav_isin_map import load_consolidated_map

    _map_cache = load_consolidated_map()
    if _map_cache:
        logger.debug("Loaded %d ISIN rows from consolidated bhav map", len(_map_cache))
    else:
        logger.warning(
            "Consolidated ISIN map is empty or missing — run "
            "`python -m pipeline.consolidate_bhav_cache` after populating data/.nse_cache "
            "or wait for the next price refresh to merge a bhav file.",
        )
    return _map_cache


def lookup_isin(isin: str) -> dict[str, Any] | None:
    """
    Return ``{"symbol": str, "name": str | None, "last_seen": str}`` for ``isin``, or ``None``.

    ``isin`` is normalised to upper case; invalid shapes return ``None``.
    """
    raw = (isin or "").strip().upper()
    if len(raw) != 12 or not raw.startswith("IN"):
        return None
    if raw in IGNORED_ISINS:
        return None
    row = _load_map().get(raw)
    if not row:
        return None
    return dict(row)


def lookup_isin_symbol(isin: str) -> str | None:
    """Return NSE symbol for ``isin``, or ``None``."""
    entry = lookup_isin(isin)
    if not entry:
        return None
    sym = (entry.get("symbol") or "").strip().upper()
    return sym or None


def lookup_isin_name(isin: str) -> str | None:
    """Return display name from bhav ``FinInstrmNm`` when available, else ``None``."""
    entry = lookup_isin(isin)
    if not entry:
        return None
    name = entry.get("name")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def lookup_isin_from_nse_bhav(isin: str) -> str | None:
    """
    Back-compat alias for :func:`lookup_isin_symbol` (same contract as the old bhav-downloader).
    """
    return lookup_isin_symbol(isin)


def update_consolidated_map_from_bhav(bhav_path: Path) -> int:
    """
    Merge one session’s bhav CSV into ``consolidated_isin_map.json`` and invalidate RAM cache.

    Returns the number of equity ISIN rows merged. Safe to call on every price refresh.
    """
    from pipeline.bhav_isin_map import (
        consolidated_isin_map_path,
        load_consolidated_map,
        merge_bhav_file_into_map,
        save_consolidated_map,
    )

    outp = consolidated_isin_map_path()
    m = load_consolidated_map(outp)
    n = merge_bhav_file_into_map(bhav_path, m)
    if n > 0:
        save_consolidated_map(m, outp)
        invalidate_bhav_isin_cache()
        logger.debug("Updated consolidated ISIN map (+ %d rows from %s)", n, bhav_path.name)
    return n
