"""
Build and refresh :class:`api.models.NseEquityReference` from NSE **Nifty indices** + **equity bhav**.

**Market cap rule (SEBI-style index buckets):**
- Symbol in **NIFTY 100** → ``LARGE_CAP``
- Else symbol in **NIFTY MIDCAP 150** → ``MID_CAP``
- Else any symbol seen in the latest **equity bhav** session → ``SMALL_CAP``

Index API rows include rich ``meta`` (company name, industry, ISIN). Bhav rows carry the
full official CSV columns for small caps and are merged into ``reference_json`` for
large/mid names when the same session is available.

Run :func:`refresh_nse_equity_reference` from ``scripts/refresh_nse_equity_reference.py``
after NSE connectivity is configured (same as price refresh).
"""

from __future__ import annotations

import datetime
import json
import logging
import time
from typing import Any

from sqlmodel import Session, delete

from api.models import NseEquityReference
from api.services.price_feed import (
    get_nse_client,
    latest_bhav_target_date,
    load_nse_equity_bhav_full_rows,
    resolve_nse_bhav_session_and_map,
)

logger = logging.getLogger(__name__)

_INDEX_THROTTLE_SEC = 0.5


def _index_stock_rows(raw_response: dict) -> list[dict]:
    """Constituent equity rows only (drop the index headline row and odd rows)."""
    data = raw_response.get("data") or []
    out: list[dict] = []
    for r in data:
        if not isinstance(r, dict):
            continue
        m = r.get("meta")
        if isinstance(m, dict) and m.get("symbol") == r.get("symbol"):
            out.append(r)
    return out


def _parse_float_cell(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def _bhav_last_price(rec: dict[str, str]) -> float | None:
    for key in ("CLSPRIC", "CLOSE", "ClsPric"):
        if key in rec:
            return _parse_float_cell(rec.get(key))
    return None


def _payload(index_row: dict | None, bhav_row: dict[str, str] | None) -> str:
    merged = {"index_row": index_row, "bhav_row": bhav_row}
    return json.dumps(merged, default=str, ensure_ascii=True)


def refresh_nse_equity_reference(session: Session, *, commit: bool = True) -> dict[str, Any]:
    """
    Replace ``nse_equity_reference`` with a fresh snapshot (Nifty 100 + Midcap 150 + bhav).

    Returns counts for logging / CLI output.
    """
    nse = get_nse_client()
    preferred = latest_bhav_target_date()
    session_d, price_map = resolve_nse_bhav_session_and_map(preferred)
    if price_map is None:
        msg = "No usable NSE equity bhav session — cannot classify small caps or merge bhav rows"
        logger.error(msg)
        raise RuntimeError(msg)

    bhav_rows = load_nse_equity_bhav_full_rows(session_d) or {}

    time.sleep(_INDEX_THROTTLE_SEC)
    n100_raw = nse.listEquityStocksByIndex("NIFTY 100")
    time.sleep(_INDEX_THROTTLE_SEC)
    m150_raw = nse.listEquityStocksByIndex("NIFTY MIDCAP 150")

    n100 = _index_stock_rows(n100_raw if isinstance(n100_raw, dict) else {})
    m150 = _index_stock_rows(m150_raw if isinstance(m150_raw, dict) else {})

    large_map: dict[str, dict] = {}
    for r in n100:
        sym = str(r.get("symbol") or "").strip().upper()
        if sym:
            large_map[sym] = r

    mid_map: dict[str, dict] = {}
    for r in m150:
        sym = str(r.get("symbol") or "").strip().upper()
        if sym:
            mid_map[sym] = r

    all_syms = set(large_map) | set(mid_map) | set(bhav_rows)

    session.exec(delete(NseEquityReference))

    n_large = n_mid = n_small = 0
    now = datetime.datetime.now(datetime.UTC)

    for sym in sorted(all_syms):
        idx_row: dict | None = None
        cap: str
        if sym in large_map:
            cap = "LARGE_CAP"
            idx_row = large_map[sym]
            n_large += 1
        elif sym in mid_map:
            cap = "MID_CAP"
            idx_row = mid_map[sym]
            n_mid += 1
        else:
            cap = "SMALL_CAP"
            n_small += 1

        br = bhav_rows.get(sym)
        meta = (idx_row or {}).get("meta") if isinstance((idx_row or {}).get("meta"), dict) else {}
        company = meta.get("companyName") if isinstance(meta.get("companyName"), str) else None
        industry = meta.get("industry") if isinstance(meta.get("industry"), str) else None
        isin = meta.get("isin") if isinstance(meta.get("isin"), str) else None
        if not company and br:
            for key in ("FININSTRMNM", "FinInstrmNm"):
                v = br.get(key)
                if v and str(v).strip():
                    company = str(v).strip()[:512]
                    break

        last_px = _parse_float_cell((idx_row or {}).get("lastPrice"))
        if last_px is None and br:
            last_px = _bhav_last_price(br)
        ffmc = _parse_float_cell((idx_row or {}).get("ffmc"))

        ref = NseEquityReference(
            symbol=sym,
            market_cap_class=cap,
            company_name=company.strip()[:512] if company else None,
            industry=industry.strip()[:256] if industry else None,
            isin=isin.strip()[:16] if isin else None,
            last_price=last_px,
            ffmc=ffmc,
            reference_json=_payload(idx_row, br),
            updated_at=now,
        )
        session.add(ref)

    if commit:
        session.commit()
    else:
        session.flush()

    out = {
        "bhav_session_date": session_d.isoformat(),
        "symbols_total": len(all_syms),
        "large_cap": n_large,
        "mid_cap": n_mid,
        "small_cap": n_small,
    }
    logger.info("nse_equity_reference refreshed: %s", out)
    return out
