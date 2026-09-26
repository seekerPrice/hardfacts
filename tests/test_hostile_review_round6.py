"""Regressions the round-6 hostile review found (docs/reviews/2026-09-26-deep-check.md)."""

import time

from hardfacts import check
from hardfacts._extract import extract


def kinds(text):
    return [(f.kind, f.text) for f in extract(text, claims=True)]


def timed(output, sources):
    t0 = time.perf_counter()
    report = check(output, sources)
    return report, time.perf_counter() - t0


# H1 --------------------------------------------------------------- huge values don't crash
def test_huge_quantities_do_not_crash_the_index():
    assert check("x 5 y", ["1" + "亿" * 600]).ok is False
    # extract(), not check(): a 4,500-digit Value is past the 1,000-digit limit the ports document
    assert [f.kind for f in extract("1" + ",000" * 1500)] == ["quantity"]


# H2 / H4 ---------------------------------- colliding keys: Evidence is capped, the scan stops
def test_many_claims_sharing_a_key_stay_fast_and_evidence_is_capped():
    report, seconds = timed("We sold 5 units. " * 3000, ["price $5, " * 3000])
    assert seconds < 3.0 and report.ok
    assert max(len(c.evidence) for c in report.claims) == 10
    _, seconds = timed("card ending in 242. " * 2500, ["id 1242 , " * 5000])
    assert seconds < 3.0


# H5 ------------------------------------- only a resource's path number is its ID
def test_only_resource_path_numbers_support_references():
    assert not check("Invoice #1500 is due.", ["https://cdn.x.com/w/1500/h/800/logo.png"]).ok
    assert not check("See #250.", ["https://blog.x.com/page/250"]).ok
    assert check("See PR #3337.", ["https://github.com/o/r/pull/3337"]).ok
    assert check("Order #48213 shipped.", ["https://shop.x.com/orders/48213"]).ok


# H6 ------------------------------------------- the hash prefix rule needs a long hash
def test_hash_prefixes_need_a_long_source_hash():
    assert not check("Your order id is abc1234.", ["order abc12345"]).ok
    assert check("Pushed as 33e41b9.", ["commit 33e41b9670c2deadbeef"]).ok


# H3 (TS divergence; Python is the reference) ------------------------------ float noise, once
def test_float_noise_is_rounded_once():
    assert not check("It is 2387.515.", ["2387.515000000001500000000"]).ok


# M1 --------------------------------------------------- the nearer of card word and time noun
def test_a_promotional_period_on_a_card_ends_in_a_year():
    assert ("identifier", "2025") not in kinds("Your credit card's promotional period ends in 2025.")
    assert ("identifier", "2024") in kinds("With your gold membership, the card ending in 2024 was charged.")


# M3 ---------------------------------------------------------------- more "now" phrasings
def test_more_ways_to_say_what_time_it_is():
    for anchor in ("It's currently 2024-05-15.", "Right now it is 2024-05-15.", "The time now is 2024-05-15."):
        assert check("Moved to 2024-05-23.", [anchor, "move it to May 23rd"]).ok, anchor


# Low --------------------------------------------------------------------- word boundaries
def test_booking_cues_are_whole_words():
    assert ("identifier", "LLAMA3") not in kinds("A triple LLAMA3 setup.")
    assert ("identifier", "XEHM82") in kinds("Your trip XEHM82 is confirmed.")
