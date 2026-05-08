"""
Regression: ICICI **Equity Transaction Statement** PDF table parse (not NSE trade mailers).

Sample PDFs under ``data/samples/icici_direct_equity/`` are gitignored; tests skip if missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SAMPLE_ANNUAL = (
    REPO
    / "data"
    / "samples"
    / "icici_direct_equity"
    / "decrypted_19d66e33a721_Equity_Transaction_Statement_from_01-Apr-2025_to_31-Mar-2026_TRX-Equity_04-04-2026_1828171.pdf"
)


def test_equity_statement_isin_regex_accepts_etf_prefix() -> None:
    """ETF / MF ISINs use ``INF*``; equity uses ``INE*`` — both are 12-char Indian ISINs."""
    from parsers.holdings.icici_direct_equity_statement_pdf import _ISIN

    assert _ISIN.match("INF109K012R6")
    assert _ISIN.match("INE397D01024")
    assert _ISIN.match("INE704P01025")
    assert not _ISIN.match("INE397D0102")
    assert not _ISIN.match("XX397D010241")


@pytest.mark.skipif(not SAMPLE_ANNUAL.is_file(), reason="sample equity statement PDF not present")
def test_annual_statement_last_grid_row_is_bharti_airtel_resolved() -> None:
    """Last trade row on the statement grid must parse (Bharti Airtel, INE397D01024 → BHARTIARTL)."""
    from parsers.holdings.icici_direct_equity_statement_pdf import (
        parse_icici_direct_equity_statement_pdf,
    )

    agg = parse_icici_direct_equity_statement_pdf(SAMPLE_ANNUAL)
    bh = [t for t in agg if t.symbol == "BHARTIARTL" and t.txn_date.isoformat() == "2026-03-30"]
    assert len(bh) == 1
    t = bh[0]
    assert t.txn_type == "BUY"
    assert t.quantity == 18.0
    assert t.total_amount == 32724.0
    assert (t.metadata or {}).get("isin") == "INE397D01024"


def test_aggregate_icici_direct_trades_merges_same_bucket() -> None:
    """Two legs same date/side/symbol → one row with summed qty and total."""
    import datetime

    from pipeline.models import InvestmentTxnType
    from parsers.holdings.base import ParsedInvestmentTxn
    from parsers.holdings.icici_direct_equity_statement_pdf import aggregate_icici_direct_trades

    d = datetime.date(2024, 1, 15)
    legs = [
        ParsedInvestmentTxn(
            txn_date=d,
            symbol="RELIANCE",
            name="RIL",
            txn_type=InvestmentTxnType.BUY.value,
            quantity=10,
            price_per_unit=2500,
            total_amount=25000,
            account_platform="ICICI Direct",
            metadata={"isin": "INE002A01018"},
        ),
        ParsedInvestmentTxn(
            txn_date=d,
            symbol="RELIANCE",
            name="RIL",
            txn_type=InvestmentTxnType.BUY.value,
            quantity=5,
            price_per_unit=2500,
            total_amount=12500,
            account_platform="ICICI Direct",
            metadata={"isin": "INE002A01018"},
        ),
    ]
    out = aggregate_icici_direct_trades(legs)
    assert len(out) == 1
    assert out[0].quantity == 15.0
    assert out[0].total_amount == 37500.0
    assert out[0].price_per_unit == pytest.approx(2500.0)
