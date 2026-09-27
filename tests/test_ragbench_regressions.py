"""Checker errors found by the blind audit of hardfacts on RAGBench (2026-09-27).

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


# Round 8 of hostile review: a bracketed value is a value, not a citation.
def test_a_bracketed_list_stated_as_the_answer_is_still_checked():
    assert not check("The scores were [7, 8, 9].", ["Scores: 7, 8 and 3."]).ok
    assert not check("The point is at coordinates [3, 4].", ["3, 5"]).ok
    assert not check("It takes [10-20] minutes.", ["10-15 minutes"]).ok
    assert not check("Aged [18–25] only.", ["Aged 18-30"]).ok
    assert not check('Response: {"qty": [2, 3]}', ["qty 2"]).ok
    assert not check("Seat [12] is yours.", ["Seat 14."]).ok
    assert not check("The answer is [42].", ["41"]).ok
    assert ("quantity", "1") in _claims("Normalize to [0, 1] first.")


def test_a_citation_list_has_at_most_six_entries():
    assert _claims("Olympic sports [1, 2, 3, 4, 5, 6, 7].") != []


# The Lancet and other UK journals write decimals with a middle dot (RAGBench audit: "fever ≥ 37·8°C").
def test_a_middle_dot_between_digits_is_a_decimal_point():
    assert check("Fever of at least 37.8°C and cough.", ["fever ≥ 37·8°C and cough"]).ok
    assert check("The rate was 12·5%.", ["12.5%"]).ok
    assert not check("The rate was 12·6%.", ["12.5%"]).ok
    assert [(c.text, c.value) for c in check("A 37·8°C fever", []).claims][0][0] == "37·8°C"


# The second RAGBench audit: dates as contracts write them (CUAD).
def test_contract_dates_the_nth_day_of_month():
    assert check("The Effective Date is March 19, 2004.", ['entered into as of the 19 day of March, 2004 (the "EFFECTIVE DATE")']).ok
    assert check("It is dated December 19, 1997.", ["made and entered into this 19th day of December 1997"]).ok
    assert not check("It is dated December 18, 1997.", ["made and entered into this 19th day of December 1997"]).ok


def test_a_year_right_after_the_comma_is_still_the_dates_year():
    assert check("The Amendment Date is October 1, 1996.", ['entered into effective October 1,1996 ("Amendment Date")']).ok
    assert not check("The Amendment Date is October 1, 1997.", ['entered into effective October 1,1996']).ok


def test_context_and_passage_citations_are_not_claims():
    assert _claims("Portugal is 92,212 sq km in total. [Context 1]") == [("quantity", "92,212")]
    assert _claims("No one was actually helping (contexts 1 and 2).") == []
    assert _claims("See [Passage 3] and [Document 2].") == []


# Space-grouped thousands right after a currency sign (the second RAGBench audit).
def test_a_space_grouped_amount_after_a_currency_sign_is_one_amount():
    assert check("The cost per live birth was $97,884.", ["a cost per live birth of $97 884 for women aged 40-42"]).ok
    assert check("It saved £244,200 a year.", ["has produced a £244 200/year cost saving"]).ok
    assert not check("It saved £244,300 a year.", ["has produced a £244 200/year cost saving"]).ok
    assert [c.text for c in check("Table 2 100 patients", []).claims] == ["2", "100"]  # plain numbers are unchanged
