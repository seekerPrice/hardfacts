from hardfacts import check


def test_a_rescaled_amount_is_supported():
    report = check("His net worth was $2.1 billion.", ["worth an estimated $2,100,000,000"])

    assert report.ok
    assert [c.kind for c in report.claims] == ["money"]


def test_a_rounded_amount_is_unsupported():
    report = check("His net worth was $2 billion.", ["worth an estimated $2.1 billion"])

    assert [c.text for c in report.unsupported] == ["$2 billion"]


def test_an_amount_in_a_different_currency_is_unsupported():
    report = check("The refund is €50.", ["Refund amount: $50"])

    assert [c.text for c in report.unsupported] == ["€50"]


def test_an_amount_is_supported_by_a_bare_number_in_a_tool_result():
    report = check("That comes to $12.50 and RM 1,200.", [{"price": 12.5, "deposit": 1200}])

    assert report.ok


def test_currency_words_after_the_number_are_money():
    report = check("You will be charged 45 dollars.", ["Late fee: USD 45"])

    assert report.ok
    assert report.claims[0].kind == "money"


def test_k_and_magnitude_words_scale_plain_quantities():
    report = check("Over 1.2k reviews and 3 million users.", ["1,200 reviews; 3,000,000 users"])

    assert report.ok


def test_a_percent_is_supported_by_the_same_percent_in_any_form():
    report = check("91% of respondents agreed; 12.5 percent did not.", ["91 percent agreed, 12.5% disagreed"])

    assert report.ok
    assert [c.kind for c in report.claims] == ["percent", "percent"]


def test_a_changed_percent_is_unsupported():
    report = check("There is a 60% chance of rain.", ["There is 63 percentage chance of rain."])

    assert [c.text for c in report.unsupported] == ["60%"]


def test_a_trailing_comma_is_not_part_of_a_number():
    report = check("They won 1, lost 3.", ["won 1 game, lost 3"])

    assert [c.text for c in report.claims] == ["1", "3"]
