from hardfacts import check


def test_list_markers_are_not_claims():
    output = "Steps:\n1. Preheat the oven.\n2) Bake for 20 minutes.\nStep 3: Serve."

    report = check(output, ["Bake the fillets for 20 minutes."])

    assert [c.text for c in report.claims] == ["20"]


def test_statements_about_the_output_length_are_not_claims():
    output = "Sure! Here's the summary within 72 words:\n\nThe council approved 3 new parks."

    report = check(output, ["The council approved three new parks."])

    assert "72" not in [c.text for c in report.claims]


def test_a_number_mid_sentence_is_still_a_claim_even_after_a_list_marker():
    report = check("1. Roast for 45 minutes.", ["Roast for 1 hour."])

    assert [c.text for c in report.unsupported] == ["45"]


def test_rating_scale_denominators_are_not_claims():
    report = check("Rated 2.0 out of 5 stars, or 4 out of 10.", [{"business_stars": 2.0, "score": 4}])

    assert [c.text for c in report.claims] == ["2.0", "4"]
