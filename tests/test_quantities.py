from hardfacts import check


def test_number_absent_from_every_source_is_unsupported():
    report = check("The order ships in 14 days.", ["Orders ship within 3 business days."])

    assert [c.text for c in report.unsupported] == ["14"]


def test_supported_claim_points_at_its_evidence_in_the_right_source():
    sources = ["Returns accepted for 30 days.", "Refunds take 7 to 10 business days."]

    report = check("Your refund will arrive in 7 to 10 business days.", sources)

    seven = report.claims[0]
    assert seven.supported
    assert [(e.source, e.span, e.text) for e in seven.evidence] == [(1, (13, 14), "7")]


def test_thousands_separators_and_trailing_zero_decimals_do_not_change_the_value():
    report = check("It costs 1200.0 in total, or 1200 before tax.", ["Total: 1,200"])

    assert report.unsupported == []


def test_structured_sources_are_searched_and_evidence_quotes_their_json_rendering():
    tool_result = {"order": {"id": "A-1", "items": 3, "weight_kg": 2.5}}

    report = check("Your 3 items weigh 2.5 kg.", [tool_result])

    assert report.unsupported == []
    assert report.claims[1].evidence[0].text == "2.5"
