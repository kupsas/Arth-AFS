"""Tests for ``pipeline.bhav_isin_map`` (bhav filename parsing and merge)."""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest

from pipeline.bhav_isin_map import (
    bhav_session_date_from_filename,
    merge_bhav_file_into_map,
    parse_bhav_equity_isin_rows,
)


def test_bhav_session_date_udiff() -> None:
    p = Path("BhavCopy_NSE_CM_0_0_0_20260507_F_0000.csv")
    assert bhav_session_date_from_filename(p) == datetime.date(2026, 5, 7)


def test_bhav_session_date_legacy() -> None:
    p = Path("cm01APR2020bhav.csv")
    assert bhav_session_date_from_filename(p) == datetime.date(2020, 4, 1)


@pytest.mark.skipif(
    not Path("data/.nse_cache/BhavCopy_NSE_CM_0_0_0_20260507_F_0000.csv").is_file(),
    reason="Local NSE cache not present in this checkout",
)
def test_parse_udiff_sample() -> None:
    p = Path("data/.nse_cache/BhavCopy_NSE_CM_0_0_0_20260507_F_0000.csv")
    rows = parse_bhav_equity_isin_rows(p)
    assert len(rows) > 1000
    nifty = next((r for r in rows if r[0] == "INF109K012R6"), None)
    assert nifty is not None
    assert nifty[1] == "NIFTYIETF"
    assert nifty[2] and "NIFTY" in nifty[2].upper()


def test_merge_bhav_updates_last_seen(tmp_path: Path) -> None:
    """Merge uses filename session date as ``last_seen``."""
    fake = tmp_path / "BhavCopy_NSE_CM_0_0_0_20260101_F_0000.csv"
    # Minimal UDIFF header + one STK EQ row (synthetic).
    fake.write_text(
        "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,"
        "XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric\n"
        '2026-01-01,2026-01-01,CM,NSE,STK,1,INE000A01001,TESTSYM,EQ,,,,,TEST CO LTD,1\n',
        encoding="utf-8",
    )
    m: dict = {}
    n = merge_bhav_file_into_map(fake, m)
    assert n == 1
    assert m["INE000A01001"]["symbol"] == "TESTSYM"
    assert m["INE000A01001"]["last_seen"] == "2026-01-01"
    assert m["INE000A01001"]["name"] == "TEST CO LTD"
