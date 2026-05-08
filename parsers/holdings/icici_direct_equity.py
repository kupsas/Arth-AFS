"""
ICICI Direct equity — **symbol resolution only** (no CSV ingest).

Annual trade CSVs and NSE “Trades executed” mailers are unsupported (no reliable ISIN).
Equity legs come from the ICICI Securities **Equity Transaction Statement** PDF parser, which
always carries ISIN; we still need broker short-code → NSE aliases and ISIN→symbol lookup
for display and price refresh alignment.
"""

from __future__ import annotations

from pipeline.icici_symbol_overrides import merge_with_disk
from pipeline.isin_nse_resolver import lookup_isin_from_nse_bhav

# Broker short codes (legacy ICICI labels in PDFs / exports). Keep keys aligned with
# ``_ICICI_BROKER_TO_NSE`` in ``api.services.price_feed`` so legacy rows still refresh.
ICICI_SHORT_TO_NSE: dict[str, str] = {
    "INTAVI": "INDIGO",
    "BAFINS": "BAJAJFINSV",
    "BANMAH": "MAHABANK",
    "BHAWIR": "BHARTIARTL",
    "HDFBAN": "HDFCBANK",
    # ICICI uses BHAELE for Bharat *Electronics* (NSE BEL). Do not map to BHEL (Heavy Electricals).
    "BHAELE": "BEL",
    "APOTYR": "APOLLOTYRE",
    "COCSHI": "COCHINSHIP",
    "ENGIND": "ENGINERSIN",
    "HDFAMC": "HDFCAMC",
    # ICICI Prud Nifty ETF: broker codes vs NSE bhav ``NIFTYIETF``.
    "ICINIF": "NIFTYIETF",
    "ICICINIFTY": "NIFTYIETF",
    "INDOIL": "IOC",
    "INTBUI": "INTERARCH",
    "INTDES": "INTELLECT",
    "KANNER": "KANSAINER",
    "LARTOU": "LT",
    "MAHGAS": "MGL",
    "NAGCON": "NCC",
    "NRBBEA": "NRBBEARING",
    "PHOMIL": "PHOENIXLTD",
    "PRAIN": "PRAJIND",
    "PVRLIM": "PVRINOX",
    "RELIND": "RELIANCE",
    "SANEN": "SANSERA",
    "SHRTRA": "SHRIRAMFIN",
    "SKFIND": "SKFINDIA",
    "TATMOT": "TATAMOTORS",
    "TATPOW": "TATAPOWER",
    "VEDLIM": "VEDL",
    "WHIIND": "WHIRLPOOL",
    "ZENSAR": "ZENSARTECH",
    "MINDAC": "MINDACORP",
    "STOONE": "STOONE",
}


def _resolve_nse_symbol(*, isin: str | None, icici_short: str) -> str:
    """Resolve ICICI short code or ISIN to the NSE ticker used in ``prices.symbol``.

    **Order:** (1) consolidated local bhav ISIN map; (2) optional ``isin_to_nse`` on disk;
    (3) ICICI broker short code → NSE via :data:`ICICI_SHORT_TO_NSE` / ``icici_short_to_nse``;
    else pass through uppercased broker code.
    """
    short_map = merge_with_disk(ICICI_SHORT_TO_NSE, "icici_short_to_nse")
    u = icici_short.strip().upper()

    if isin:
        iso = isin.strip().upper()
        sym_bhav = lookup_isin_from_nse_bhav(iso)
        if sym_bhav:
            return sym_bhav
        isin_overrides = merge_with_disk({}, "isin_to_nse")
        if iso in isin_overrides:
            return isin_overrides[iso]

    return short_map.get(u, u)


def resolve_icici_direct_nse_symbol(
    *,
    isin: str | None = None,
    icici_short: str = "",
) -> str:
    """Resolve symbol for an equity leg when we have ISIN (preferred) and/or ICICI short code.

    Ingest paths that lack ISIN are not supported; this function is used by the equity
    statement PDF parser (ISIN-first) and by trade aggregation helpers.

    Keeps holdings price refresh aligned with :func:`api.services.price_feed.canonical_nse_symbol`.
    """
    return _resolve_nse_symbol(isin=isin, icici_short=icici_short)
