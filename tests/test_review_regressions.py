"""Bugs found in code review (matt-code-review, Standards axis), reproduced through check()."""

from hardfacts import check


def test_upper_case_money_magnitudes_scale_the_amount():
    report = check("Valued at $2.1B, raised $5M and $5 Million.", ["valued at $2.1 billion after raising $5 million"])

    assert report.ok


def test_a_lower_case_letter_after_a_number_is_not_a_temperature_scale():
    report = check("Drop a 5c coin in.", ["Drop a coin in."])

    assert [c.kind for c in report.claims] != ["temperature"]


def test_a_chinese_ordinal_is_not_a_count():
    report = check("第二十五届大会。", ["The 25th congress."])

    assert report.claims == ()


def test_a_domain_is_supported_by_an_email_address_at_that_domain():
    report = check("Visit acme.com for details.", ["Contact info@acme.com"])

    assert report.ok


# ------------------------------------------------------------------------- Spec axis


def test_suffix_magnitudes_scale_plain_quantities():
    report = check("It has 3M users and 3bn page views.", ["3,000,000 users; 3 billion views"])

    assert report.ok
    assert [c.value for c in report.claims] == [3_000_000, 3_000_000_000]


def test_money_is_not_supported_by_the_unscaled_digits_of_a_bigger_number():
    report = check("Refund of $2.1 and growth of 15%.", ["Revenue was 2.1 billion; 15 million users"])

    assert [c.text for c in report.unsupported] == ["$2.1", "15%"]


def test_a_source_on_the_24_hour_clock_reads_bare_times_as_24_hour():
    report = check("Opens at 9 PM.", ["Hours: 9:00-17:00, Sat 10:00-14:00"])

    assert [c.text for c in report.unsupported] == ["9 PM"]


def test_a_phone_claim_cannot_invent_an_area_code():
    report = check("Call +1 510 889 8690.", ["Call 889-8690"])

    assert [c.text for c in report.unsupported] == ["+1 510 889 8690"]


def test_json_report_carries_the_rendered_sources():
    report = check("Weighs 2.5 kg.", [{"weight_kg": 2.5}])

    data = report.to_dict()
    e = data["claims"][0]["evidence"][0]
    assert data["sources"][e["source"]][e["span"][0]:e["span"][1]] == "2.5"
