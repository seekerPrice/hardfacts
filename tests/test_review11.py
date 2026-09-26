"""Round 11: a whole-library adversarial review (2026-09-27), not a diff review."""

from hardfacts import check


def _values(output):
    return [(c.kind, c.text, str(c.value)) for c in check(output, []).claims]


# Chinese shorthand: a lone digit after 万/千/百 counts the next unit down.
def test_chinese_shorthand_after_wan_qian_bai():
    assert check("您的退款为一万五。", [{"refund": 15000}]).ok
    assert not check("您的退款为一万五。", [{"refund": 10005}]).ok
    assert check("一百五十人", [{"n": 150}]).ok
    assert check("一共一百五。", [{"total": 150}]).ok
    assert check("两千五块", [{"total": 2500}]).ok
    assert check("一万零五", [{"n": 10005}]).ok  # 零 keeps the digit in the ones place


# European format: dots group thousands, a comma marks decimals.
def test_european_thousands_and_decimal_comma():
    assert check("Total: 1.500,00 €", [{"refund": 1500}]).ok
    assert not check("Total: €1.5", ["Gesamt: 1.500,00 €"]).ok
    assert check("€1,500", ["Gesamt: 1.500,00 €"]).ok


# Lakh and crore are magnitudes.
def test_lakh_and_crore_are_magnitudes():
    assert not check("Your loan is ₹5 lakh.", [{"loan_amount": 5, "tenure_years": 5}]).ok
    assert check("Your loan is ₹5 lakh.", [{"loan_amount": 500000}]).ok
    assert check("It costs 2 crore rupees.", [{"price": 20000000}]).ok


# Minor units on their own are money: 50 sen is RM0.50.
def test_sen_cents_and_cent_sign_are_minor_units():
    assert not check("A service fee of 50 sen applies.", [{"service_fee": 50.0, "currency": "MYR"}]).ok
    assert check("A service fee of 50 sen applies.", [{"service_fee": 0.5, "currency": "MYR"}]).ok
    assert not check("The fee is 50¢.", [{"fee": 50}]).ok
    assert check("The fee is 50 cents.", [{"fee": 0.5}]).ok


# A bare JSON amount is in the currency its Source names.
def test_a_claimed_currency_must_match_the_currency_the_source_names():
    refund = {"refund": {"amount": 50, "currency": "MYR"}}
    assert check("Your refund of RM 50 is on its way.", [refund]).ok
    assert not check("Your refund of USD 50 is on its way.", [refund]).ok
    assert not check("Your refund of €50 is on its way.", [refund]).ok
    assert not check("Your refund of $50 is on its way.", [refund]).ok


def test_a_source_naming_no_currency_or_several_still_supports():
    assert check("Your refund of $50 is on its way.", [{"refund": 50}]).ok
    assert check("Your refund of $50 is on its way.", [{"refund": 50, "currencies": ["MYR", "USD"]}]).ok
    assert check("Your refund of RM 50 is on its way.", [{"refund": 50}, {"note": "prices in USD"}]).ok  # another Source's currency


# A year-less date borrows the year that puts it nearest the current date.
def test_a_year_less_date_near_new_year_borrows_the_nearest_year():
    source = [{"current_date": "Today is 2025-12-30.", "eta": "Jan 2"}]
    assert check("It arrives January 2, 2026.", source).ok
    assert not check("It arrives January 2, 2025.", source).ok
    back = [{"current_date": "Today is 2026-01-03.", "ordered": "Dec 28"}]
    assert check("You ordered on December 28, 2025.", back).ok
    assert check("Your flight is on 2024-05-23.", ["The current time is 2024-05-15.", "Move it to May 23rd."]).ok
