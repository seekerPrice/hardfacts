"""Regressions the round-3 hostile review found in the tau-bench-era changes (docs/reviews/2026-09-26-deep-check.md)."""

import time

from hardfacts import check
from hardfacts._extract import extract


def timed(output, sources):
    t0 = time.perf_counter()
    report = check(output, sources)
    return report, time.perf_counter() - t0


# H1 ---------------------------------------------- total Derivation work is bounded per check
def test_many_flagged_values_do_not_make_the_derivation_search_slow():
    supported = [str(100 + i * 13) for i in range(60)]
    invented = [str(900000 + i) for i in range(400)]
    _, seconds = timed("Readings: " + ", ".join(supported) + ". Other readings: " + ", ".join(invented) + ".",
                       ["Readings: " + ", ".join(supported)])
    assert seconds < 1.0
    many = [f"${1000 + i}.{i % 100:02d}" for i in range(1000)]
    _, seconds = timed(" ".join(many) + " " + " ".join(f"${5 + i}.001" for i in range(100)), [" ".join(many)])
    assert seconds < 2.0


# H2 --------------------------------------------------------- long mask runs scan linearly
def test_long_runs_of_mask_characters_are_linear():
    for text in ("*" * 50000, "x" * 50000, "XXXX XXXX " * 5000, "xxxx-xxxx-xxxx-xxxx " * 1000, "•" * 20000):
        _, seconds = timed(text, [])
        assert seconds < 1.0


# H3 / H4 ------------------------------------ a year-less date takes only the conversation's year
def test_a_year_less_date_takes_only_an_anchor_year():
    assert not check("Your appointment is on 5 August 2023.",
                     [{"appointment": "August 5", "created_at": "2023-01-01T00:00:00Z", "now": "2024-07-30"}]).ok
    assert check("Your appointment is on 5 August 2024.",
                 [{"appointment": "August 5", "created_at": "2023-01-01T00:00:00Z", "now": "2024-07-30"}]).ok
    assert not check("The recall began on October 12, 2011.",
                     ["The recall began on October 12.", "Earlier recalls: 2011-02-01 and 2016-08-09."]).ok
    assert not check("on 23 May 2020", ["on 23 May. Report dated 01/02/2020."]).ok


def test_year_less_expansion_stays_fast_with_many_dates():
    months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
              "November", "December"]
    source = ". ".join(f"{1900 + i}-01-01" for i in range(100)) + ". " + ". ".join(
        f"on {months[i % 12]} {1 + (i * 7) % 28}" for i in range(500))
    output = ". ".join(f"It happened on {months[i % 12]} {1 + (i * 3) % 28}, {1850 + i % 40}" for i in range(300))
    _, seconds = timed(output, [source])
    assert seconds < 1.0


# H5 ---------------------------------------------------- Markdown bold is not a card mask
def test_markdown_bold_numbers_are_ordinary_numbers():
    assert not check("Take **500** mg twice daily.", ["Take 1500 mg twice daily."]).ok
    assert not check("**Total seats:** 150", ["Total seats: 1150"]).ok
    assert not check("Rating 4.5 •• 1200 reviews", ["Rating 4.5, 21200 reviews"]).ok
    assert not check("Of the scores, the last 3 are 151, 200 and 250.", ["Scores: 1151, 200, 250"]).ok
    assert [(c.kind, c.value[1]) for c in check("**Price:** 1200 dollars", []).claims] == [("money", 1200)]
    assert check("Your Visa **** 4242 was charged.", [{"card": {"last4": "4242"}}]).ok
    assert check("Card ***4242 on file.", ["card_7384242"]).ok


# H6 ----------------------------------------------- short ID segments don't vouch for amounts
def test_short_id_segments_do_not_support_unrelated_amounts():
    assert not check("Your order total is $2,500.", [{"order_id": "ORD-2500", "total": 180}]).ok
    assert not check("We shipped 3668 units.", [{"user_id": "mia_li_3668", "units": 12}]).ok
    assert not check("Growth was 1200%.", ["ticket TKT-1200 opened"]).ok
    assert check("I charged the card ending 7574394.", [{"payment_method_id": "credit_card_7574394"}]).ok
    assert check("Card 7574394 was charged.", [{"payment_method_id": "credit_card_7574394"}]).ok
    assert not check("That costs $7574394.", [{"payment_method_id": "credit_card_7574394"}]).ok


# M1 ----------------------------------------------------- derivations keep to one currency
def test_derivations_do_not_mix_currencies():
    report = check("The hotel is €100 and the tour is $40, so you pay $60 more for the hotel.", ["hotel €100, tour $40"])
    assert [(c.text, c.derivation) for c in report.unsupported] == [("$60", None)]
    report = check("RM 50 plus $30 means ¥80 total.", ["RM 50 and $30"])
    assert [(c.text, c.derivation) for c in report.unsupported] == [("¥80", None)]
    assert check("It's $101.12 and yours was USD 94.80: $6.32 more.", [{"a": 94.8, "b": 101.12}]).unsupported[0].derivation


# M2 ---------------------------------------------------- "ends in 2025" is usually a year
def test_a_year_after_ends_in_is_a_year():
    assert check("Your mobile plan ends in 2025.", ["Contract end date: 2025-06-30"]).ok
    assert check("The account's fiscal year ending in 2024 showed a loss.", ["Fiscal year ended 31 March 2024 with a loss."]).ok
    assert check("Your card ending in 2024 was charged.", [{"card": "credit_card_1112024"}]).ok


# M3 --------------------------------------- a Source's "May 19 and 20" supports "May 19th and 20th"
def test_a_non_ordinal_range_in_a_source_supports_an_ordinal_one():
    assert check("The workshop is on May 19th and 20th.", ["The workshop is on May 19 and 20."]).ok


# M4 ------------------------------------------ last digits need an ID, a phone or the digits themselves
def test_last_digits_are_not_supported_by_any_number_ending_in_them():
    assert not check("Card ending in 500 was charged.", [{"price": 1500}]).ok
    assert not check("Card **** 2024 was charged.", ["We have served 12024 customers. Card 4111111111111111"]).ok
    assert check("Card **** 1111 was charged.", ["Card 4111111111111111"]).ok


# L1 ------------------------------------------------ float noise lives in the last digits
def test_only_binary_noise_is_rounded():
    assert not check("Value 5.1000000000009 units", ["Value 5.1 units"]).ok
    assert check("A refund of $3.76 will be issued.", [{"amount": 3.759999999999991}]).ok
    assert check("Refunded $0.35.", [{"amount": 0.3499999999999943}]).ok


# L2 ------------------------------------------ six-character names ending in a version digit
def test_model_names_ending_in_a_digit_need_a_booking_cue_to_be_codes():
    assert check("WE FINE-TUNED LLAMA3 ON THE DATA.", ["We fine-tuned Llama 3 on the data."]).ok
    assert not check("Your reservation FDZ4T6 is confirmed.", [{"reservation_id": "FDZ4T5"}]).ok


# L3 --------------------------------------------------------------- "3rd place" is not a date
def test_an_ordinal_rank_after_and_is_not_a_date():
    assert ("date", "3rd") not in [(f.kind, f.text) for f in extract("In May 2nd and 3rd place teams met.")]


# Found fixing the above, by diffing tau-bench flags -----------------------------------------
def test_a_source_reads_a_booking_code_without_a_cue():
    user = {"name": "Mia", "reservations": ["7WPL39", "3EMQJ6", "A90KR2", "X1Y2Z3", "Q9W8E7", "9MRJD4"]}
    assert check("Looking up reservation_id 9MRJD4 now.", [user]).ok


def test_three_last_digits_can_end_an_id_but_not_a_price():
    assert check("Refunded to your gift card ending in 803.", [{"payment_method_id": "gift_card_4332803"}]).ok
    assert not check("Card ending in 500 was charged.", [{"price": 1500}]).ok


# The TS parity reviewer's findings (round 3) ----------------------------------------------
def test_derivations_are_exact_beyond_28_digits():
    a, b = "999999999999999999999999999999", "1000000000000000000000000000000"
    report = check(f"A ${a} and ${b}: ${int(a) + int(b)} in all.", [f"${a} and ${b}"])
    assert report.unsupported[0].derivation.expression == f"${a} + ${b}"


def test_pathological_lengths_stay_fast():
    # extract(), not check(): a 40,000-digit Value is past the 1,000-digit limit the ports document
    # (docs/port-parity.md), so it must not enter the recorded conformance fixture
    for text in ("1." + "9" * 40000, "card ending" + " " * 20000 + "1234", "last four digits" + " " * 20000 + "5678"):
        t0 = time.perf_counter()
        extract(text)
        assert time.perf_counter() - t0 < 1.0
    many = " ".join(f"${10 + i}" for i in range(16)) + " " + " ".join(f"${10 ** 9 + i}" for i in range(200))
    _, seconds = timed(many, [" ".join(f"${10 + i}" for i in range(16))])
    assert seconds < 0.5


def test_non_string_keys_render_as_json_writes_them():
    assert check("", [{True: 5, None: 6, 7: 8}]).sources[0] == '{"7": 8, "true": 5, "null": 6}'
