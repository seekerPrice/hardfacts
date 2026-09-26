"""Hedged numbers ("over 60 days") are matched exactly, like any other number (ADR-0006)."""

from hardfacts import check


def test_a_hedged_round_number_is_not_widened_into_a_range():
    # Widening was measured on RAGTruth train: "over 15 years" got support from an
    # unrelated "19", and "over 100 sites" from "175-foot". Net loss, so rejected.
    report = check("He was adrift for over 60 days.", ["hadn't been heard from in 66 days"])

    assert [c.text for c in report.unsupported] == ["60"]
