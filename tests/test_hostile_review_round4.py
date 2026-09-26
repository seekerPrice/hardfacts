"""Regressions the round-4 hostile review found in the round-3 fixes (docs/reviews/2026-09-26-deep-check.md)."""

import time

from hardfacts import check
from hardfacts._extract import extract


def kinds(text):
    return [(f.kind, f.text) for f in extract(text, claims=True)]


# H1 ---------------------------------- a record locator ending in a digit is a code without a cue
def test_record_locators_in_lists_and_tables_are_codes():
    assert not check("Your flight XEHM82 is confirmed.", [{"reservation_id": "XEHM83"}]).ok
    assert not check("1. **FDZ4T6**\n2. **X7BYG2**", [{"reservations": ["FDZ4T5", "X7BYG1"]}]).ok
    assert check("WE FINE-TUNED LLAMA3 ON THE DATA.", ["We fine-tuned Llama 3 on the data."]).ok  # a name: one digit, last


# H2 ------------------------------------------ the nearer noun decides "ends in <year>"
def test_a_card_that_ends_in_a_year_like_number_is_a_card_reference():
    assert ("identifier", "2024") in kinds("Your Visa card ends in 2024.")
    assert ("identifier", "2024") in kinds("With your gold membership, the card ending in 2024 was charged.")
    assert ("identifier", "2025") not in kinds("Your mobile plan ends in 2025.")


# H3 -------------------------------------------- only a word-joined Source range vouches
def test_a_hyphen_range_does_not_vouch_for_a_count():
    assert not check("There were 12 speakers.", ["Held March 10-12, 2015."]).ok
    assert check("The workshop is on May 19th and 20th.", ["The workshop is on May 19 and 20."]).ok


# H4 ------------------------------------------------ float keys render as json.dumps writes them
def test_float_keys_render_as_json_writes_them():
    assert check("", [{1e20: "x", 1.0: "y"}]).sources[0] == '{"1e+20": "x", "1.0": "y"}'


# H5 / H6 --------------------------------------------------------------- bounded work
def test_last_n_digits_of_and_many_amounts_stay_fast():
    t0 = time.perf_counter()
    extract("last 4 digits of" + " " * 20000 + "x")
    assert time.perf_counter() - t0 < 0.5
    amounts = " ".join(f"${100 + i}.{i % 97:02d}" for i in range(2000))
    t0 = time.perf_counter()
    check(amounts + " " + " ".join(f"${9000 + i}.001" for i in range(200)), [amounts])
    assert time.perf_counter() - t0 < 2.0


# M1 / M2 ------------------------------------------------------ real card masks, bold or short
def test_bold_and_short_card_masks_are_card_references():
    assert check("Charged to the card ending in **1234**.", [{"card": "credit_card_7771234"}]).ok
    assert check("Charged to **Visa •••• 4242**.", [{"card": {"last4": "4242"}}]).ok
    for text in ("Visa ••4242", "card xx-4242", "XX4242 on file"):
        assert ("identifier", "4242") in kinds(text), text
    assert ("identifier", "1200") not in kinds("Rating 4.5 •• 1200 reviews")
    assert ("identifier", "500") not in kinds("Take **500** mg")


# M3 -------------------------------------------------------------- more ways to say "now"
def test_current_date_fields_lend_their_year():
    for source in ({"current_date": "2024-05-15"}, {"currentDate": "2024-05-15"}, "It is currently 2024-05-15."):
        assert check("Moved to 2024-05-23.", [source, "move it to May 23rd"]).ok, source
