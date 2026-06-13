"""Consolidated ISIN map lookups (local JSON, no live NSE)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from pipeline import isin_nse_resolver


def test_lookup_isin_invalid_returns_none() -> None:
    assert isin_nse_resolver.lookup_isin_from_nse_bhav("") is None
    assert isin_nse_resolver.lookup_isin_from_nse_bhav("FOO") is None
    assert isin_nse_resolver.lookup_isin_from_nse_bhav("INE002A0101") is None  # short


def test_lookup_isin_uses_consolidated_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        isin_nse_resolver,
        "_load_map",
        lambda: {
            "INE002A01018": {"symbol": "RELIANCE", "name": "RELIANCE INDUSTRIES LTD", "last_seen": "2026-01-01"},
        },
    )
    assert isin_nse_resolver.lookup_isin_from_nse_bhav("ine002a01018") == "RELIANCE"
    assert isin_nse_resolver.lookup_isin_name("ine002a01018") == "RELIANCE INDUSTRIES LTD"


def test_lookup_isin_blocked_list_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        isin_nse_resolver,
        "_load_map",
        lambda: {"INE148I01020": {"symbol": "STOONE", "name": "STONE INDIA LTD", "last_seen": "2020-01-01"}},
    )
    assert isin_nse_resolver.lookup_isin_from_nse_bhav("INE148I01020") is None
    assert isin_nse_resolver.lookup_isin("INE148I01020") is None


def test_sorilinfra_isin_is_blocked_without_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """Curated blocklist — SORILINFRA must not resolve even if present in consolidated JSON."""
    monkeypatch.setattr(
        isin_nse_resolver,
        "_load_map",
        lambda: {"INE034H01016": {"symbol": "SORILINFRA", "name": "X", "last_seen": "2020-01-01"}},
    )
    assert isin_nse_resolver.lookup_isin_from_nse_bhav("INE034H01016") is None


def test_curated_ignore_matches_symbol_storing_raw_isin() -> None:
    """Parser aggregation can put the ISIN in ``symbol`` when bhav lookup is blocked."""
    assert isin_nse_resolver.is_curated_ignored_security(symbol="INE034H01016", isin=None)
    assert isin_nse_resolver.is_curated_ignored_security(symbol="SORILINFRA", isin=None)
    assert not isin_nse_resolver.is_curated_ignored_security(symbol="RELIANCE", isin="INE002A01018")


def test_curated_ignore_holding_row_uses_getattr_no_isin_attr() -> None:
    """ORM ``Holding`` may not expose ``isin``; filtering must not access ``.isin``."""
    row = SimpleNamespace(symbol="INE034H01016")
    assert isin_nse_resolver.is_curated_ignored_holding_row(row)
    assert not isin_nse_resolver.is_curated_ignored_holding_row(SimpleNamespace(symbol="RELIANCE"))


def test_load_map_bootstraps_when_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty on-disk map triggers one bootstrap attempt before giving up."""
    isin_nse_resolver.invalidate_bhav_isin_cache()
    monkeypatch.setattr(isin_nse_resolver, "_bootstrap_attempted", False)
    calls: list[bool] = []

    def _fake_bootstrap() -> bool:
        calls.append(True)
        return True

    loads = iter(
        [
            {},
            {
                "INE002A01018": {
                    "symbol": "RELIANCE",
                    "name": "RELIANCE",
                    "last_seen": "2026-01-01",
                },
            },
        ]
    )

    monkeypatch.setattr(
        "pipeline.bhav_isin_map.load_consolidated_map",
        lambda *a, **k: next(loads),
    )
    monkeypatch.setattr(isin_nse_resolver, "_try_bootstrap_consolidated_map", _fake_bootstrap)
    m = isin_nse_resolver._load_map()
    assert calls == [True]
    assert m["INE002A01018"]["symbol"] == "RELIANCE"
    isin_nse_resolver.invalidate_bhav_isin_cache()
    monkeypatch.setattr(isin_nse_resolver, "_bootstrap_attempted", False)
