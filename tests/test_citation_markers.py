"""Bracketed citation markers point at sources; they state nothing (RAGBench audit, 2026-09-27).

24 of the 30 "not a claim" flags on RAGBench were markers like "[10]" or "[1, 2, 3, 4, 5]".
"""

from hardfacts import check


def _claims(output, sources=()):
    return [(c.kind, c.text) for c in check(output, list(sources)).claims]


def test_bracketed_citation_markers_are_not_claims():
    assert _claims("Around 800,000 civilians were killed [10].") == [("quantity", "800,000")]
    assert _claims("It is the dominant language [2, 3, 5, 6].") == []
    assert _claims("Olympic disciplines [1,2,3,5].") == []
    assert _claims("A preference for positive self-views [1-6].") == []
    assert _claims("As reported [^2] and [Doc 3] and [Source 4].") == []


def test_a_cited_sentence_is_still_checked():
    report = check("The Nobel Prize came in 1962 [1, 5].", ["He won the Nobel Prize in 1963."])
    assert [(c.text, c.supported) for c in report.claims] == [("1962", False)]


def test_bracketed_values_that_are_not_citations_are_still_claims():
    assert ("quantity", "101") in _claims("The affected IDs are [101, 102].")
    assert ("quantity", "2024") in _claims("The term ended [2024].")


def test_a_list_in_a_source_is_still_evidence():
    assert check("There are 3 slots left.", ['{"slots": [1, 2, 3]}']).ok
