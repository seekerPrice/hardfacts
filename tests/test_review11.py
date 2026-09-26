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
    assert check("It arrives January 2, 2025.", source).ok  # round 12: the anchor year stays a reading (doubt)
    back = [{"current_date": "Today is 2026-01-03.", "ordered": "Dec 28"}]
    assert check("You ordered on December 28, 2025.", back).ok
    assert check("Your flight is on 2024-05-23.", ["The current time is 2024-05-15.", "Move it to May 23rd."]).ok



# Round 12 of hostile review.
def test_only_a_currency_key_in_the_same_json_names_the_currency():
    for source in ({"refund": {"amount": 50, "currency": "myr"}, "note": "USD accepted"},
                   {"refund": 50, "currency_symbol": "RM", "fx": "USD rate unavailable"},
                   {"refund": 50, "price_display": "$12"},
                   {"refund": 50, "stack": "PHP"},
                   {"fare": 50, "currency": "RM", "alt_currency": "SGD"}):
        assert check("Your refund of RM 50 is on its way.", [source]).ok, source
    assert not check("Your refund of USD 50 is on its way.", [{"refund": {"amount": 50, "currency": "myr"}}]).ok


def test_a_currency_blocked_source_is_skipped_in_linear_time():
    import time
    start = time.perf_counter()
    check("USD 5 " * 4000, [{"items": [5] * 4000, "currency": "MYR"}])
    assert time.perf_counter() - start < 5


def test_the_anchor_year_stays_and_no_invalid_leap_day_is_made():
    source = [{"current_date": "Today is 2025-12-30.", "ordered": "Mar 5"}]
    assert check("You ordered on March 5, 2025.", source).ok
    assert check("It shipped on February 29, 2024.", [{"current_date": "Today is 2024-10-15.", "shipped": "Feb 29"}]).ok


def test_european_numbers_need_a_clean_left_edge():
    assert not check("It weighs 1,500.12 kg.", ['{"w":[1.500,12]}']).ok
    assert check("12 items", ['{"w":[0.125,12]}']).ok
    assert check("Total 1.500,00 EUR.", [{"total": 1500}]).ok


# Round 13 of hostile review.
def test_money_evidence_states_its_own_currency_whatever_the_currency_key_says():
    assert check("The fee is RM12.", [{"currency": "USD", "remark": "local fee RM12"}]).ok
    assert check("It is RM 50.", [{"items": [{"amount": 100, "currency": "USD"}], "note": "Total RM 50"}]).ok


def test_a_json_string_source_names_its_currency_too():
    assert not check("It costs USD 50.", ['{"amount": 50, "currency": "MYR"}']).ok
    assert not check("It costs USD 50.", [{"order": '{"amount": 50, "currency": "MYR"}'}]).ok
    assert check("It costs RM 50.", ['{"amount": 50, "currency": "MYR"}']).ok


def test_a_european_amount_after_a_bracket_is_still_read():
    assert check("It costs EUR 1,500.", ["Preise [1.500,00 EUR]"]).ok
    assert not check("It costs EUR 1.5.", ["Preise [1.500,00 EUR]"]).ok


def test_currency_keys_are_matched_by_word():
    assert check("It costs USD 50.", [{"amount": 50, "recurring": "yen"}]).ok
    assert not check("It costs MYR 50.", [{"amount": 50, "ccy_code": "USD"}]).ok
    assert not check("It costs MYR 50.", [{"amount": 50, "currencyCode": "USD"}]).ok


def test_the_six_month_window_counts_days():
    assert check("It arrives 1 June 2026.", ["Today is 31 December 2025. ETA Jun 1."]).ok
    assert check("It arrives 29 February 2028.", ["Today is 15 August 2027. ETA Feb 29."]).ok


# Round 14 of hostile review.
def test_deeply_nested_json_text_is_not_parsed_and_does_not_crash():
    for n in (1000, 100000):
        check("It costs USD 50.", ["[" * n + "]" * n])


def test_an_anchor_date_that_does_not_exist_lends_no_neighbouring_year():
    check("It arrives 2 July 2025.", ["Today is 31 April 2025. ETA Jul 2."])
    check("It arrives 2 January 2025.", ["Today is 30 February 2025. ETA Jan 2."])
