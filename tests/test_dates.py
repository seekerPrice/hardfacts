from hardfacts import check


def test_a_date_restated_with_less_detail_is_supported():
    report = check("She died before February 7.", ["The Red Cross records give February 7 (1945) as the date."])

    assert report.ok
    assert report.claims[0].kind == "date"


def test_a_date_restated_with_an_invented_year_is_unsupported():
    report = check("She died on February 7, 2022.", ["The Red Cross records give February 7 (1945) as the date."])

    assert [c.text for c in report.unsupported] == ["February 7, 2022"]


def test_iso_dates_in_tool_results_support_written_dates():
    review = {"review_date": "2022-01-16 14:45:22"}

    report = check("A review from January 16, 2022 (posted 16 Jan 2022, on Jan. 16th).", [review])

    assert report.ok
    assert [c.kind for c in report.claims] == ["date", "date", "date"]


def test_a_month_and_year_needs_both_in_the_source():
    assert check("The trial began in March 2015.", ["The trial began March 28, 2015."]).ok
    assert not check("The trial began in March 2015.", ["The trial began March 28."]).ok


def test_a_wrong_day_is_unsupported():
    report = check("NPR reported it on May 28th.", ["On May 27, NPR reported the protests."])

    assert [c.text for c in report.unsupported] == ["May 28th"]


def test_a_bare_year_is_supported_by_a_full_date_in_that_year():
    report = check("He was released in 2014.", ["released on 2014-06-09 after talks"])

    assert report.ok


def test_an_ambiguous_numeric_date_is_supported_by_either_reading():
    report = check("Valid until 03/04/2022.", ["Offer ends 4 March 2022."])

    assert report.ok


def test_report_values_use_x_for_unstated_date_parts():
    report = check("Due March 2015 and on May 28.", [])

    assert report.to_dict()["unsupported"][0]["value"] == ["2015-03-XX"]
    assert report.to_dict()["unsupported"][1]["value"] == ["XXXX-05-28"]


def test_a_sentence_full_stop_after_a_month_is_not_part_of_the_date():
    report = check("It arrives for the 4th of July.", ["Expected on July 4."])

    assert [c.text for c in report.claims] == ["4th of July"]
    assert report.ok
