"""Checker errors found by the blind audit of the held-out tau2-bench run.

docs/reviews/2026-09-26-tau2bench-results.md tabulates them. Everything here was fixed after
the held-out score, so runs after it are post-fix, not out-of-sample.
"""

from hardfacts import check


def _claims(output, sources=()):
    return [(c.kind, c.text) for c in check(output, list(sources)).claims]


# Telecom agents list network generations with slashes: alternatives, not one code.
def test_slash_joined_network_generations_are_a_list_not_an_identifier():
    policy = "The user can switch to a network mode that includes 3G, 4G, or 5G."
    assert check("Set it to 5G/4G/3G/2G Auto.", ["prefers to connect to (e.g., 5G, 4G, 3G, 2G)"]).ok
    assert check("Choose 3G/4G/5G.", [policy]).ok
    assert check("Try 5G/4G/3G/etc.", [policy]).ok
    assert ("identifier", "5G/4G/3G/2G") not in _claims("Set it to 5G/4G/3G/2G Auto.")
    assert not check("Choose 3G/4G/6G.", [policy]).ok  # each generation is still checked


def test_slash_joined_measures_are_a_list():
    assert check("Speeds of 100Mbps/20Mbps.", ["100Mbps down, 20Mbps up"]).ok
    assert not check("Speeds of 100Mbps/30Mbps.", ["100Mbps down, 20Mbps up"]).ok
    # a model name keeps a spec one identifier ("i5/32GB/256GB"): the name is checked with it
    assert check("It has i5/32GB/256GB.", ["i5/32GB/256GB"]).ok


def test_slash_joined_codes_are_still_one_identifier():
    assert ("identifier", "INV/2024/0012") in _claims("Invoice INV/2024/0012 is paid.")
    assert ("identifier", "12A/12B") in _claims("Seats 12A/12B are yours.")
    assert ("identifier", "A1/B2/C3") in _claims("SKU A1/B2/C3 is in stock.")


# A user quotes a URL and ends the sentence inside the quotes: “…/wapenc.”
def test_a_sentence_full_stop_inside_closing_curly_quotes_is_not_part_of_a_url():
    user = "the MMSC URL is “http://mms.carrier.com/mms/wapenc.”"
    assert check('Your MMSC URL "http://mms.carrier.com/mms/wapenc" looks right.', [user]).ok
    assert check("See ‘https://example.com/help’ for more.", ["https://example.com/help"]).ok


# A phone line is referred to by its last digits.
def test_a_line_ending_in_digits_is_a_last_digit_reference():
    line = {"line_id": "L1002", "phone_number": "555-123-2002", "status": "Suspended"}
    assert check("Your line ending in 2002 is currently suspended.", [line]).ok
    assert check("The line ending in 2001 is on the Basic Plan.", [{"phone_number": "555-123-2001"}]).ok
    assert not check("Your line ending in 2003 is currently suspended.", [line]).ok


def test_an_ellipsis_before_the_last_digits_is_a_mask():
    card = {"id": "gift_card_7711863"}
    assert check("Refunded to your gift card ending in …1863.", [card]).ok
    assert check("Refunded to your gift card ending in ...1863.", [card]).ok
    assert not check("Refunded to your gift card ending in …1864.", [card]).ok


# Month/day dates with no year, when the order can't be misread: one part is over 12.
def test_an_unambiguous_numeric_month_day_is_a_date():
    flight = {"flight_number": "HAT298", "date": "2024-05-19"}
    assert check("HAT298 departs on 5/19.", [flight]).ok
    assert check("Your connection via ATL on 05/22.", [{"date": "2024-05-22"}]).ok
    assert check("Your connection via ATL on 22/05.", [{"date": "2024-05-22"}]).ok
    assert not check("HAT298 departs on 5/20.", [flight]).ok
    assert ("date", "5/19") in _claims("on 5/19")
    assert ("date", "5/22") in _claims("from 5/19 to 5/22")
    assert check("Savings from 3/19 - 3/30/2017.", ["Weekly ad, 3/19 - 3/30/2017: $31.12"]).ok
    assert check("Savings from 3/31 - 4/16/2017.", ["Weekly ad, valid 3/31 - 4/16/2017: $1.98"]).ok


def test_ambiguous_or_fraction_like_slashes_stay_numbers():
    assert ("date", "1/2") not in _claims("Add 1/2 cup.")
    assert ("date", "5/6") not in _claims("Rated 5/6.")
    assert _claims("Open 24/7.") == []
    assert ("date", "13/20") not in _claims("A score of 13/20.")
    assert ("date", "3/15") not in _claims("This is step 3/15.")
    assert ("date", "5/19/2024") in _claims("on 5/19/2024")  # the full date is untouched


# "May 27 and 28, 2024": the year after a worded range belongs to both days.
def test_a_worded_day_range_with_a_year_keeps_the_year():
    days = [{"date": "2024-05-27"}, {"date": "2024-05-28"}]
    assert check("Return flights on May 27 and 28, 2024.", days).ok
    assert not check("Return flights on May 27 and 29, 2024.", days).ok
    assert ("quantity", "6") in _claims("Seats for May 5 and 6 people.")  # a count still follows


# Round 7 of hostile review: regressions in the fixes above.
def test_a_fraction_in_a_source_never_vouches_for_a_date():
    assert not check("Your refund arrives on March 16.", ["Use a 3/16 inch drill bit."]).ok
    assert not check("The sale ends September 16.", ["The screen ratio is 16/9."]).ok
    assert check("Your refund arrives on March 16.", ["Refund due by 3/16."]).ok


def test_a_fraction_in_an_output_without_a_date_word_stays_two_numbers():
    assert check("3/15 tickets were sold.", ["3 out of 15 tickets were sold."]).ok
    assert check("The team won 7/13 games.", ["7 of 13 games"]).ok


def test_a_model_name_in_a_slash_run_is_still_checked():
    assert not check("Core i7/16GB/1TB laptop", ["Core i5/16GB/1TB"]).ok
    assert not check("M2/16GB/512GB", ["M3/16GB/512GB"]).ok
    assert check("4G/LTE is on.", ["4G LTE"]).ok


def test_a_curly_apostrophe_inside_a_url_path_is_part_of_it():
    assert not check("Visit https://shop.com/o’neill-jacket", ["https://shop.com/o’brien-jacket"]).ok
    assert check("Visit https://shop.com/o’neill-jacket", ["https://shop.com/o’neill-jacket"]).ok


def test_a_year_after_a_line_ending_is_a_year():
    assert check("Your line ends in 2025.", ["Your line contract ends 31 December 2025."]).ok
    assert check("Your line ending in 2025 is active.", [{"phone_number": "555-123-2025"}]).ok
    assert check("Your line ends in …2025.", [{"phone_number": "555-123-2025"}]).ok
