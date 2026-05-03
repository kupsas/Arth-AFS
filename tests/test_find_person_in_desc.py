"""Tests for ``_find_person_in_desc`` two-word ordered subsequence matching."""

from pipeline.rules_classifier import (
    _find_person_in_desc,
    _tokens_contain_ordered_sequence,
)


def test_ordered_subsequence_adjacent():
    assert _tokens_contain_ordered_sequence(["A", "B", "C"], ["A", "B"]) is True


def test_ordered_subsequence_non_adjacent():
    assert _tokens_contain_ordered_sequence(["RAHUL", "SHEKHAWAT", "SINGH"], ["RAHUL", "SINGH"]) is True


def test_ordered_subsequence_reversed_order():
    assert _tokens_contain_ordered_sequence(["SINGH", "SHEKHAWAT", "RAHUL"], ["RAHUL", "SINGH"]) is False


def test_find_person_two_words_extra_middle_matches_forward_order():
    """Rahul Singh vs Rahul Shekhawat Singh — both tokens appear in order."""
    desc = "IMPS-REF-Rahul Shekhawat Singh-ACC"
    assert (
        _find_person_in_desc(desc, ["Rahul Singh"])
        == "Rahul Singh"
    )


def test_find_person_two_words_bank_flipped_last_first():
    """Bank prints Shekhawat before Rahul."""
    desc = "NEFT SHEKHAWAT RAHUL REF123"
    assert _find_person_in_desc(desc, ["Rahul Shekhawat"]) == "Rahul Shekhawat"


def test_find_person_substring_still_works():
    assert _find_person_in_desc("X Rahul Shekhawat Y", ["Rahul Shekhawat"]) == "Rahul Shekhawat"


def test_find_person_three_word_word_set_unchanged():
    """Existing ≥3 word subset behaviour."""
    desc = "KRISHNA KUPPA VENKATA VINOD"
    assert (
        _find_person_in_desc(desc, ["VENKATA VINOD KRISHNA KUPPA"])
        == "VENKATA VINOD KRISHNA KUPPA"
    )


def test_find_person_upi_narration_two_words_with_middle_name_in_bank_field():
    """UPI lines put legal name in the structured field; two-word contacts should still match.

    Hyphens are normalised to spaces so ``ADITI``, ``ABHAY``, ``LOTLIKAR`` become
    separate tokens and ordered two-word matching finds ``ADITI`` … ``LOTLIKAR``.
    """
    desc = (
        "UPI-ADITI ABHAY LOTLIKAR-aditi.lotlikar-1@okaxis-ICIC0006434-608837687667-"
        "Splitwise settle Ref 608837687667"
    )
    assert _find_person_in_desc(desc, ["Aditi Lotlikar"]) == "Aditi Lotlikar"
