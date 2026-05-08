"""
Build and maintain a local ISIN → NSE symbol (+ display name) map from NSE bhav CSVs.

Bhav files live under ``data/.nse_cache`` (gitignored). The consolidated JSON is the
authoritative source for :mod:`pipeline.isin_nse_resolver` so equity parsing does not
depend on live NSE downloads.
"""

from __future__ import annotations

import csv
import datetime
import json
import logging
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from nse import NSE

from pipeline.config import REPO_ROOT

logger = logging.getLogger(__name__)

# Same default as ``api.services.price_feed.NSE_DOWNLOAD_DIR``.
DEFAULT_NSE_CACHE_DIR = REPO_ROOT / "data" / ".nse_cache"
DEFAULT_CONSOLIDATED_PATH = DEFAULT_NSE_CACHE_DIR / "consolidated_isin_map.json"
DEFAULT_DELISTED_CANDIDATES_PATH = DEFAULT_NSE_CACHE_DIR / "delisted_isin_candidates.json"

# Equity cash series we keep (exclude bonds, T-bills, etc. in legacy bhav).
_LEGACY_EQUITY_SERIES = frozenset({"EQ", "BE", "BZ"})

_UDIFF_NAME = re.compile(r"BhavCopy_NSE_CM_0_0_0_(\d{8})_F_0000\.csv$", re.IGNORECASE)
_LEGACY_NAME = re.compile(r"^cm(\d{2})([A-Z]{3})(\d{4})bhav\.csv$", re.IGNORECASE)


def consolidated_isin_map_path() -> Path:
    """Path to consolidated JSON (override with ``ARTH_ISIN_MAP_PATH`` for tests)."""
    raw = os.environ.get("ARTH_ISIN_MAP_PATH", str(DEFAULT_CONSOLIDATED_PATH))
    return Path(raw).resolve()


def _is_valid_indian_isin(isin: str) -> bool:
    u = (isin or "").strip().upper()
    return len(u) == 12 and u.startswith("IN")


def bhav_session_date_from_filename(path: Path) -> datetime.date | None:
    """Infer NSE session calendar date from a cached bhav filename."""
    name = path.name
    m = _UDIFF_NAME.search(name)
    if m:
        ymd = m.group(1)
        try:
            return datetime.date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))
        except ValueError:
            return None
    m = _LEGACY_NAME.match(name)
    if not m:
        return None
    day_s, mon_s, year_s = m.group(1), m.group(2), m.group(3)
    try:
        day = int(day_s)
        year = int(year_s)
    except ValueError:
        return None
    mon_map = {
        "JAN": 1,
        "FEB": 2,
        "MAR": 3,
        "APR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AUG": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DEC": 12,
    }
    month = mon_map.get(mon_s.upper())
    if month is None:
        return None
    try:
        return datetime.date(year, month, day)
    except ValueError:
        return None


def iter_bhav_cache_csv_paths(cache_dir: Path) -> list[Path]:
    """Return sorted equity bhav CSV paths under ``cache_dir`` (newest last)."""
    if not cache_dir.is_dir():
        return []
    paths: list[Path] = []
    for p in cache_dir.iterdir():
        if not p.is_file() or not p.name.lower().endswith(".csv"):
            continue
        if bhav_session_date_from_filename(p) is None:
            continue
        paths.append(p)
    paths.sort(key=lambda x: bhav_session_date_from_filename(x) or datetime.date.min)
    return paths


def _parse_udiff_bhav(path: Path) -> list[tuple[str, str, str | None]]:
    """Return (isin, tckr_symb, fin_instr_nm or None) equity rows from a UDIFF bhav file."""
    out: list[tuple[str, str, str | None]] = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return out
        h = {k.upper(): k for k in reader.fieldnames}
        need = ("ISIN", "TCKRSYMB", "FININSTRMTP", "SCTYSRS")
        if not all(k in h for k in need):
            return out
        for row in reader:
            if (row.get(h["FININSTRMTP"]) or "").strip().upper() != "STK":
                continue
            series = (row.get(h["SCTYSRS"]) or "").strip().upper()
            if series not in _LEGACY_EQUITY_SERIES:
                continue
            isin = (row.get(h["ISIN"]) or "").strip().upper()
            sym = (row.get(h["TCKRSYMB"]) or "").strip().upper()
            if not _is_valid_indian_isin(isin) or not sym:
                continue
            nm_key = "FININSTRMNM" if "FININSTRMNM" in h else None
            name = (row.get(h[nm_key]) or "").strip() if nm_key else None
            out.append((isin, sym, name or None))
    return out


def _parse_legacy_cm_bhav(path: Path) -> list[tuple[str, str, str | None]]:
    """Return (isin, symbol, None) equity rows from legacy ``cm*bhav.csv``."""
    out: list[tuple[str, str, str | None]] = []
    with open(path, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return out
        h = {k.upper().strip(): k for k in reader.fieldnames if k}
        if "ISIN" not in h or "SYMBOL" not in h or "SERIES" not in h:
            return out
        for row in reader:
            series = (row.get(h["SERIES"]) or "").strip().upper()
            if series not in _LEGACY_EQUITY_SERIES:
                continue
            isin = (row.get(h["ISIN"]) or "").strip().upper()
            sym = (row.get(h["SYMBOL"]) or "").strip().upper()
            if not _is_valid_indian_isin(isin) or not sym:
                continue
            out.append((isin, sym, None))
    return out


def parse_bhav_equity_isin_rows(path: Path) -> list[tuple[str, str, str | None]]:
    """Parse one cached bhav file into equity (isin, symbol, optional name) rows."""
    session = bhav_session_date_from_filename(path)
    if session is None:
        return []
    if session >= NSE.UDIFF_SWITCH_DATE:
        return _parse_udiff_bhav(path)
    return _parse_legacy_cm_bhav(path)


def _atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".isin_map_",
        suffix=".tmp",
    )
    try:
        os.write(fd, text.encode("utf-8"))
        os.close(fd)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def save_consolidated_map(data: dict[str, dict[str, Any]], path: Path | None = None) -> None:
    """Atomically write the consolidated ISIN map JSON."""
    _atomic_write_json(path or consolidated_isin_map_path(), data)


def load_consolidated_map(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load ``{ISIN: {symbol, name, last_seen}}`` from disk; empty dict if missing."""
    p = path or consolidated_isin_map_path()
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read consolidated ISIN map %s: %s", p, e)
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            continue
        ku = k.strip().upper()
        if not _is_valid_indian_isin(ku):
            continue
        sym = (v.get("symbol") or "").strip().upper()
        if not sym:
            continue
        out[ku] = {
            "symbol": sym,
            "name": v.get("name"),
            "last_seen": (v.get("last_seen") or "")[:10],
        }
    return out


def merge_bhav_file_into_map(
    bhav_path: Path,
    mut_map: dict[str, dict[str, Any]],
    *,
    session_date: datetime.date | None = None,
) -> int:
    """
    Merge one bhav file into ``mut_map`` (mutated in place).

    Returns the number of ISIN rows applied.
    """
    d = session_date or bhav_session_date_from_filename(bhav_path)
    if d is None:
        logger.debug("Could not infer session date from bhav path %s", bhav_path)
        return 0
    rows = parse_bhav_equity_isin_rows(bhav_path)
    n = 0
    last_seen = d.isoformat()
    for isin, sym, name in rows:
        prev = mut_map.get(isin)
        entry: dict[str, Any] = {"symbol": sym, "last_seen": last_seen}
        if name:
            entry["name"] = name
        elif prev and prev.get("name"):
            entry["name"] = prev["name"]
        else:
            entry["name"] = None
        mut_map[isin] = entry
        n += 1
    return n


def write_delisted_candidates(
    consolidated: dict[str, dict[str, Any]],
    *,
    out_path: Path,
    latest_session: datetime.date,
    lookback_days: int = 180,
) -> None:
    """
    Write ISINs whose ``last_seen`` is before ``latest_session - lookback_days``.

    These are *candidates* for delisting / suspension — human review still required
    before adding to ``IGNORED_ISINS`` in code.
    """
    threshold = latest_session - datetime.timedelta(days=lookback_days)
    thr_s = threshold.isoformat()
    candidates: list[dict[str, Any]] = []
    for isin, meta in sorted(consolidated.items()):
        ls = (meta.get("last_seen") or "")[:10]
        if not ls or ls >= thr_s:
            continue
        candidates.append(
            {
                "isin": isin,
                "symbol": meta.get("symbol"),
                "name": meta.get("name"),
                "last_seen": ls,
            }
        )
    payload = {
        "as_of": latest_session.isoformat(),
        "threshold_date": thr_s,
        "lookback_calendar_days": lookback_days,
        "candidate_count": len(candidates),
        "candidates": candidates,
    }
    _atomic_write_json(out_path, payload)
    logger.info(
        "Wrote %d delisted/suspended ISIN candidates to %s",
        len(candidates),
        out_path.name,
    )


def consolidate_all_cached_bhavs(
    cache_dir: Path | None = None,
    *,
    out_path: Path | None = None,
    candidates_path: Path | None = None,
    lookback_days: int = 180,
) -> dict[str, dict[str, Any]]:
    """
    Scan all bhav CSVs in chronological order and write ``consolidated_isin_map.json``.

    Latest file wins per ISIN for symbol/name; ``last_seen`` tracks the last session
    that listed the ISIN.
    """
    base = cache_dir or DEFAULT_NSE_CACHE_DIR
    outp = out_path or consolidated_isin_map_path()
    candp = candidates_path or DEFAULT_DELISTED_CANDIDATES_PATH
    mut: dict[str, dict[str, Any]] = {}
    paths = iter_bhav_cache_csv_paths(base)
    for p in paths:
        merge_bhav_file_into_map(p, mut)
    _atomic_write_json(outp, mut)
    logger.info("Wrote consolidated ISIN map (%d ISINs) → %s", len(mut), outp)
    latest = max(
        (d for p in paths if (d := bhav_session_date_from_filename(p)) is not None),
        default=None,
    )
    if latest is not None:
        write_delisted_candidates(mut, out_path=candp, latest_session=latest, lookback_days=lookback_days)
    return mut
