"""Findings confirmed by the deep-check audit (docs/reviews/2026-09-26-deep-check.md), each reproduced first."""

from hardfacts import check


def verdicts(output, sources, **kw):
    return [(c.kind, c.text, c.supported) for c in check(output, sources, **kw).claims]


# A1 ------------------------------------------------------------ ISO datetimes in tool results
def test_iso_datetime_keeps_its_hour_and_the_offset_is_not_a_time():
    eta = [{"eta": "2026-10-03T14:00:00+08:00"}]
    assert check("Your parcel arrives on 3 October at 2 PM.", eta).ok
    assert not check("Your parcel arrives on 3 October at 8 AM.", eta).ok
    assert not check("Your parcel arrives on 3 October at 8 PM.", eta).ok


# A2 -------------------------------------------------------- CJK amounts with thousands commas
def test_cjk_amounts_keep_their_leading_thousands_group():
    assert not check("退款2,200元", ["退款1,200元"]).ok
    assert check("退款1,200元已处理", [{"refund": 1200}]).ok
    assert not check("用户达1,500万人", ["用户达500万人"]).ok


# A3 -------------------------------------------------- one-letter words after a price
def test_a_hyphenated_word_after_a_price_is_not_a_magnitude():
    assert check("Grab the RM20 T-shirt today!", [{"item": "T-shirt", "price": 20}]).ok
    assert check("The $25 K-pop album is back.", [{"price_usd": 25}]).ok
    assert check("It raised $3M last year.", ["raised $3,000,000"]).ok


# A4 / A24 --------------------------------------------- non-breaking spaces and full-width digits
def test_non_breaking_spaces_are_spaces():
    assert check("Raised $2.1 billion; closes at 9:00 PM.", ["Raised $2.1 billion; closes 9:00 PM"]).ok
    assert not check("The shop closes at 9 AM.", ["Closes 9:00 PM"]).ok
    assert check("Delivery on 3 October 2026", ["ETA 3 October 2026"]).ok


def test_full_width_digits_are_digits():
    assert check("Order 1234 costs 50%.", ["订单１２３４，折扣５０％"]).ok


# A5 / A27 --------------------------------------------- grouped numbers are not phone numbers
def test_dot_and_space_grouped_numbers_are_not_phones():
    assert check("Harga baru ialah Rp 1.500.000.", [{"harga": 1500000}]).ok
    assert verdicts("Harga Rp 1.500.000", [{"harga": "Rp 2.500.000"}], kinds={"money"}) == [("money", "Rp 1.500.000", False)]
    assert check("Revenue grew to 142 in 2023.", ["Year 2021 2022 2023\nRevenue 125 138 142"]).ok


def test_rupiah_uses_dots_for_thousands():
    assert check("Harganya Rp 50.000 sahaja.", [{"price": 50000}]).ok


# A6 ------------------------------------------------------------- unformatted phone numbers
def test_unformatted_and_formatted_phones_match_both_ways():
    assert check("Call us at 012-345 6789.", [{"phone": "0123456789"}]).ok
    assert check("Call us at +60123456789.", [{"phone": "+60 12-345 6789"}]).ok
    assert verdicts("Call us at 0123456780.", [{"phone": "0123456789"}], kinds={"phone"}) == [("phone", "0123456780", False)]
    assert check("Call 6123 4567 for support.", [{"phone": "+65 6123 4567"}]).ok


# A7 / B-01 ------------------------------------------------ digit-only codes and #tags
def test_digit_only_tracking_numbers_are_identifiers():
    report = check("Your FedEx tracking number is 794612345679.", [{"tracking": "794612345678"}], kinds={"identifier"})
    assert [(c.kind, c.supported) for c in report.claims] == [("identifier", False)]
    assert check("Tracking 794612345678.", [{"tracking": 794612345678}]).ok


def test_a_number_tag_matches_the_same_number_without_the_hash():
    assert check("Your ticket #48213 is open.", [{"ticket_id": 48213}]).ok
    assert check("Your ticket 48213 is open.", ["Ticket #48213 opened"]).ok
    assert not check("Your ticket #48214 is open.", [{"ticket_id": 48213}]).ok


# A8 ------------------------------------------------------------------------- dotted times
def test_dotted_times_with_a_meridiem_are_times():
    assert check("Opens 9.30am, closes 10.30pm.", [{"hours": "09:30-22:30"}]).ok
    assert check("Buka 9.30 pagi hingga 5.00 petang.", [{"hours": "09:30-17:00"}]).ok
    assert verdicts("It costs 9.30 dollars", ["9.30"])[0][0] == "money"


# A10 / A15 / A21 ---------------------------------------------------- small exemption bugs
def test_out_of_a_large_number_is_still_a_claim():
    assert not check("3 out of 10,000 users complained.", ["3 of 1,000 users"]).ok


def test_temperatures_keep_thousands_commas():
    assert not check("It melts at 2,000°F.", ["melts at 1,000°F"]).ok


def test_character_limits_are_facts_not_output_length():
    assert not check("Tweets are limited to 300 characters.", ["Tweets are limited to 280 characters."]).ok


# A11 --------------------------------------------------------- CJK idioms inside real numerals
def test_cjk_idioms_do_not_swallow_real_numerals():
    assert check("会议持续30分钟。", ["会议持续三十分钟。"]).ok
    assert check("预算5000万元。", ["预算五千万元。"]).ok
    assert check("我们十分重视。", ["无关"]).ok  # the idiom on its own is still not a claim


# A9 --------------------------------------------------------- the 24-hour rule needs a real time
def test_a_ratio_does_not_switch_a_text_to_the_24_hour_clock():
    # The other half of A9 (a timestamp field switching its record to the 24-hour clock) is intended:
    # Yelp-style records write hours as "10:0-4:0" next to "18:40:30" timestamps (refuted as a defect).
    assert check("Doors open at 8:00.", ["The widescreen format is 16:9. Doors open at 8:00 PM"]).ok


# A12 ------------------------------------------------------------- Chinese decimals and 万亿
def test_chinese_decimal_point_and_stacked_units():
    assert check("融资一点五亿美元", ["融资1.5亿美元"]).ok
    assert not check("融资一点五亿美元", ["融资5亿美元"]).ok
    assert check("市场规模达一万亿元", ["市场规模达1万亿元"]).ok


# A16 / A17 / A18 / A19 / A22 ------------------------------------------------------ dates
def test_day_first_dates_win_over_a_month_first_reading():
    assert check("Delivery on 3 Oct 26.", [{"eta": "2026-10-03"}]).ok
    assert check("Delivery slot 3 Oct 9 am.", [{"slot": "2026-10-03 09:00"}]).ok
    assert check("Event on 5 May, 12 people came", ["12 people came on 5 May"]).ok


def test_day_month_year_with_hyphens_is_a_date():
    report = check("Expires 3-Oct-2026 (03-OCT-26).", [{"expiry": "2026-10-03"}])
    assert [c.kind for c in report.claims] == ["date", "date"] and report.ok


def test_day_first_ranges_support_both_ends():
    assert check("Starts 3 October, ends 5 October 2026.", ["Runs 3–5 October 2026."]).ok


def test_malay_hb_day_suffix():
    assert check("Dihantar pada 3hb Oktober 2026.", [{"hantar": "2026-10-03"}]).ok
    assert not check("Dihantar pada 4hb Oktober 2026.", [{"hantar": "2026-10-03"}]).ok


def test_mac_laptops_and_may_percentages_are_not_dates():
    assert check("We supplied 5 Mac laptops to the office.", ["The office received 5 laptops."]).ok
    assert check("In May 5% of users churned.", ["In May, 5% of users churned."]).ok


# A20 --------------------------------------------------------------- number-word ranges
def test_number_word_ranges_yield_both_numbers():
    report = check("The survey covered between fifteen and twenty clinics.", ["The survey covered 40 clinics."])
    assert [c.text for c in report.unsupported] == ["fifteen", "twenty"]
    assert [c.text for c in check("the first twenty minutes", ["20 minutes"]).claims] == ["twenty"]


# A23 ----------------------------------------------------------------- adversarial input
def test_long_dotted_runs_are_linear_time():
    import time

    t0 = time.perf_counter()
    check("a." * 20000 + "comx", ["visit x.com " + "a." * 10000])
    assert time.perf_counter() - t0 < 1.0


# B-03 ------------------------------------------------------------- JSON float rendering
def test_small_and_large_json_floats_render_as_plain_decimals():
    assert check("The rate is 0.00005 per call, cap 10000000000000000.", [{"rate": 0.00005, "cap": 1e16}]).ok


# B-04 --------------------------------------------------------------- sources must be a list
def test_a_bare_string_or_dict_as_sources_is_an_error_not_silent_iteration():
    import pytest

    with pytest.raises(TypeError, match="list"):
        check("Refund RM 45", "refund RM 45")
    with pytest.raises(TypeError, match="list"):
        check("Refund RM 45", {"refund": 45})


# B-10 ---------------------------------------------------------------- long exact values
def test_values_beyond_28_digits_stay_exact():
    tracking = "9400111202555842761044123456789012"  # 34-digit USPS-style code
    report = check(f"Tracking {tracking}.", [{"tracking": tracking}])
    assert report.ok and report.to_dict()["claims"][0]["value"] == tracking
    big = check("It holds 1234567890123456789012345678901.5 million units.", [])
    assert big.to_dict()["claims"][0]["value"] == "1234567890123456789012345678901500000"
