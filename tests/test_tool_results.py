"""Tool-result patterns found by the blind audit of hardfacts on tau-bench (bench/taubench.py).

Support agents answer from JSON their tools computed, and real tools leak float
noise, snake_case IDs and year-less dates the user typed.
"""

from hardfacts import check


# Float noise: a tool computed 302.67 - 298.91 in binary floating point.
def test_float_noise_in_a_tool_result_is_the_rounded_value():
    assert check("A refund of $3.76 will be issued.", [{"amount": 3.759999999999991}]).ok
    assert check("Refunded $0.35.", [{"amount": 0.3499999999999943}]).ok
    assert check("You paid $17.86 more.", [{"amount": 17.860000000000014}]).ok
    assert not check("A refund of $3.75 will be issued.", [{"amount": 3.759999999999991}]).ok
    assert not check("A refund of $3.77 will be issued.", [{"amount": 3.759999999999991}]).ok


def test_long_decimals_without_float_noise_are_kept_as_written():
    assert not check("Pi is about 3.14.", ["pi = 3.14159265358979"]).ok
    assert check("Pi is 3.14159265358979.", ["pi = 3.14159265358979"]).ok


# snake_case IDs: the number in "credit_card_7574394" is stated.
def test_the_number_in_a_snake_case_id_is_stated():
    assert check("I charged the card ending 7574394.", [{"payment_method_id": "credit_card_7574394"}]).ok
    assert not check("I charged the card ending 7574395.", [{"payment_method_id": "credit_card_7574394"}]).ok
    assert check("Use gift card 4332117.", [{"id": "gift_card_4332117"}]).ok


# A date the user typed without a year takes the year the conversation states.
def test_a_year_less_date_takes_the_year_the_sources_state():
    policy, user = "The current time is 2024-05-15 15:00:00 EST.", "I want to move my return flight to May 23rd."
    assert check("Your return flight is now on 2024-05-23.", [policy, user]).ok
    assert check("Your return flight is now on May 23, 2024.", [policy, user]).ok
    assert not check("Your return flight is now on 2024-05-24.", [policy, user]).ok
    assert not check("Your return flight is now on 2025-05-23.", [policy, user]).ok
    assert not check("Your return flight is now on 2024-05-23.", [user]).ok  # no year anywhere


# Ordinal day ranges joined by a word (a known miss since the v0.1 audit).
def test_ordinal_day_ranges_joined_by_and():
    flights = [{"flights": [{"date": "2024-05-19"}, {"date": "2024-05-20"}]}]
    assert check("You fly on May 19th and 20th.", flights).ok
    assert not check("You fly on May 19th and 21st.", flights).ok
    assert check("It runs October 20th and 21st, 2023.", [{"days": ["2023-10-20", "2023-10-21"]}]).ok


# Objects keyed by IDs render in one order in both ports: JavaScript's, the only order JSON.parse keeps.
def test_integer_keys_render_first_in_numeric_order_as_javascript_orders_them():
    source = {"4510078629": 1, "1355937109": 2, "b": 3, "0": 4, "007": 5, "4294967294": 6, "4294967295": 7}
    assert check("", [source]).sources[0] == (
        '{"0": 4, "1355937109": 2, "4294967294": 6, "4510078629": 1, "b": 3, "007": 5, "4294967295": 7}')


# Whole floats render as JavaScript renders them: JSON.parse has no 1518.0, only 1518.
def test_whole_floats_render_without_a_trailing_zero():
    assert check("", [{"amount": 1518.0, "zero": -0.0, "big": 1e16, "cents": 46.5}]).sources[0] == (
        '{"amount": 1518, "zero": 0, "big": 10000000000000000, "cents": 46.5}')
    assert check("You paid $1,518.", [{"amount": 1518.0}]).ok


# "Ending in 1784" is a less specific statement of gift_card_1591784 (Specificity, CONTEXT.md).
def test_last_digits_are_supported_by_a_number_ending_in_them():
    gift_card = [{"payment_method_id": "gift_card_1591784"}]
    assert check("I'll refund it to your gift card ending in 1784.", gift_card).ok
    assert not check("I'll refund it to your gift card ending in 2692.", [{"payment_method_id": "gift_card_7250692"}]).ok
    assert check("Your Visa **** 4242 was charged.", [{"card": {"brand": "visa", "last4": "4242"}}]).ok
    assert check("The last four digits of your phone are 5678.", [{"phone": "+60 12-345 5678"}]).ok
    assert not check("The last four digits of your phone are 5679.", [{"phone": "+60 12-345 5678"}]).ok
    assert check("Card xxxx-4242 is on file.", ["Card on file: •••• 4242"]).ok


def test_a_full_number_is_not_supported_by_its_last_digits():
    assert not check("Your gift card is 1591784.", ["gift card ending in 1784"]).ok


def test_an_ending_without_an_account_word_is_an_ordinary_number():
    report = check("The season ending in 2024 was long.", ["The 2024 season"])
    assert [(c.kind, c.text, c.supported) for c in report.claims] == [("quantity", "2024", True)]


def test_day_first_ranges_joined_by_and():
    assert check("It runs October 20th and 21st, 2023.", ["Held on 20 and 21 October 2023"]).ok
    assert not check("It runs October 19th and 21st, 2023.", ["Held on 20 and 21 October 2023"]).ok
