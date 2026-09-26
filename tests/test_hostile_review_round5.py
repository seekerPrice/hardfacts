"""Regressions the round-5 hostile review found (docs/reviews/2026-09-26-deep-check.md)."""

import time

from hardfacts import check
from hardfacts._extract import extract


def kinds(text):
    return [(f.kind, f.text) for f in extract(text, claims=True)]


def timed(output, sources):
    t0 = time.perf_counter()
    report = check(output, sources)
    return report, time.perf_counter() - t0


# H1 -------------------------------------------- a number in a URL path is an ID, not a count
def test_url_path_numbers_support_references_not_counts():
    sources = ["https://github.com/o/r/pull/250", "https://github.com/o/r/issues/12", "http://x.com/users/3/orders/2"]
    assert not check("The PR removes 250 lines and adds 12 tests after 3 retries.", sources).ok
    assert check("See PR #250 and issue #012.", sources).ok is False  # "#012" is not "12"
    assert check("See PR #250.", sources).ok


# H2 ---------------------------------------------- an Output hash may be shorter, never longer
def test_a_longer_hash_is_more_specific_than_its_source():
    assert check("Pushed as 33e41b9.", ["commit 33e41b9670c2deadbeef"]).ok
    assert not check("Pushed as 33e41b9670c2deadbeef.", ["[main 33e41b9] fix"]).ok
    assert not check("Your token is a1b2c3d4e5f6.", ["token a1b2c3d4"]).ok


# H3 ------------------------------------------------ "currently" alone is a status, not today
def test_only_the_conversations_date_lends_a_year():
    assert not check("Delivery on March 3, 2023.", ["Order currently estimated 2023-12-01; delivery March 3"]).ok
    assert check("Moved to 2024-05-23.", ["It is currently 2024-05-15.", "move it to May 23rd"]).ok


# H4 / H5 / H6 --------------------------------------- matching is indexed, not claims × evidence
def test_large_inputs_match_in_linear_time():
    codes = " ".join(f"AB{i:04d}" for i in range(8000))  # ~55 KB of six-character codes
    _, seconds = timed(codes, [codes])
    assert seconds < 3.0
    ranges = " ".join(f"March {1 + i % 27}-{2 + i % 27}, {1990 + i % 30}" for i in range(2500))
    _, seconds = timed(ranges, [ranges])
    assert seconds < 3.0


# M1 ---------------------------------------------- letters then a version number is a name
def test_names_with_a_trailing_version_number_are_not_booking_codes():
    for name in ("BASE64", "UINT32", "HTTP11", "SAVE20", "XMAS24", "LLAMA3"):
        assert ("identifier", name) not in kinds(f"We use {name} here."), name
    assert not check("Your flight XEHM82 is confirmed.", [{"reservation_id": "XEHM83"}]).ok
    assert not check("1. **FDZ4T6**", [{"reservations": ["FDZ4T5"]}]).ok


# M2 ------------------------------------------------- a time noun wins unless a card is named
def test_a_trial_on_an_account_ending_in_a_year_is_a_year():
    assert check("The free trial on your account ends in 2025.", ["Trial ends 2025-03-31."]).ok
    assert ("identifier", "2024") in kinds("Your Visa card ends in 2024.")


# L2 ------------------------------------------------------ "March 10 to 12" is a range
def test_a_to_range_does_not_vouch_for_a_count():
    assert not check("There were 12 speakers.", ["Held March 10 to 12, 2015."]).ok
