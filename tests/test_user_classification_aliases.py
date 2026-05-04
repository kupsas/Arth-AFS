"""Tests for self-alias loading used by rules-based self-transfer detection."""

from api.services.user_classification import normalize_self_aliases_for_matching


def test_normalize_self_aliases_uppercases_and_dedupes():
    assert normalize_self_aliases_for_matching(["Ada", "ADA", " ada "]) == ["ADA"]


def test_normalize_self_aliases_preserves_order_first_wins():
    out = normalize_self_aliases_for_matching(["Kuppa Sai", "kuppa sai"])
    assert out == ["KUPPA SAI"]


def test_normalize_self_aliases_collapses_internal_whitespace():
    assert normalize_self_aliases_for_matching(["Sai   Sashank\tKuppa"]) == ["SAI SASHANK KUPPA"]


def test_normalize_self_aliases_skips_empty():
    assert normalize_self_aliases_for_matching(["", "   ", "OK"]) == ["OK"]
