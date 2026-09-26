"""Checker errors found by auditing RAGTruth train false positives (bench/audit/train)."""

from hardfacts import check


def test_a_date_used_as_a_heading_is_still_a_date():
    report = check("April 16th:\n* 48 degrees and cloudy", ["The forecast for Apr 16 is 48 degrees and Cloudy."])

    assert report.ok


def test_midnight_written_with_am_is_a_time():
    report = check("Open from 0:00 AM to 0:00 AM on Mondays.", [{"hours": {"Monday": "0:0-0:0"}}])

    assert report.ok


def test_unicode_fractions_are_values():
    report = check("About 23.5 inches of ash; the jury deliberated 11.5 hours.", ["About 23½ inches of ash fell. After deliberating for 11½ hours"])

    assert report.ok


def test_a_leading_dot_decimal_is_a_value():
    report = check("She owns about 0.9% of US farmland.", ["owns around .9 percent of American farmland"])

    assert report.ok


def test_references_to_the_outputs_own_steps_and_citations_are_not_claims():
    report = check("Repeat steps 6 and 7, then step 4 (Passage 2, Fact 5). See Review 2.", ["Rinse and repeat."])

    assert report.claims == ()


def test_a_day_range_supports_both_ends():
    report = check("The event runs from March 10, 2015 to March 12, 2015.", ["It takes place March 10-12, 2015."])

    assert report.ok


def test_a_word_hyphen_number_compound_is_a_quantity():
    report = check("A 7.8 magnitude quake struck.", ["when the magnitude-7.8 earthquake broke out"])

    assert report.ok


def test_numbers_fused_to_common_units_are_quantities():
    report = check("The pump restarts at 30 psi and 3000 rpm.", ["drops to around 30psi, spinning at 3000rpm"])

    assert report.ok


def test_escape_sequences_in_json_sources_do_not_hide_numbers():
    # json.dumps writes a newline inside a string as backslash-n, glued to the next digit.
    report = check("Their 2018 reserve; waits of 40-50 minutes.", [
        {"review": "Great service.\n40-50 minutes wait though."},  # rendered as ...service.\\n40-50...
        r"'review_text': 'their\xa02018 Reserve Cabernet'",  # a Python repr with a literal \xa0
    ])

    assert report.ok


def test_a_time_range_gives_its_meridiem_to_the_first_end():
    report = check("Open Tuesdays 5-9 pm.", [{"hours": {"Tuesday": "17:0-21:0"}}])

    assert report.ok


def test_n_word_summary_statements_are_not_claims():
    report = check("Here is a 94-word summary of the article:", ["Summarize within 90 words."])

    assert report.claims == ()


def test_large_ordinal_words_are_values():
    report = check("On day 11, 200 miles off the coast.", ["On the eleventh day, 200 miles off the coast"])

    assert report.ok
