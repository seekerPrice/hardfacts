"""Regressions the hostile review of the deep-check fixes found (docs/reviews/2026-09-26-deep-check.md, round 2).

Each one was a behaviour the pre-fix tree got right and the first round of fixes broke.
"""

import time

from hardfacts import check
from hardfacts._extract import extract


def kinds(text):
    return [(f.kind, f.text) for f in extract(text)]


# H1 -------------------------------------------------------- number-word runs stay linear
def test_long_runs_of_number_words_are_fast():
    for text in ("one and " * 800, "one " * 800, " and ".join(["one two three four five six seven eight"] * 100)):
        t0 = time.perf_counter()
        extract(text)
        assert time.perf_counter() - t0 < 1.0


# H2 --------------------------------------------- long integers in JSON still support amounts
def test_long_integers_support_money_and_money_supports_long_integers():
    assert check("Market cap is $2.5 billion.", [{"market_cap": 2500000000}]).ok
    assert check("$2,500,000,000", ["market cap 2500000000"]).ok
    assert check("RM 1,200,000,000", [{"revenue": 1200000000}]).ok
    assert check("1.2 billion ringgit", [{"revenue_myr": 1200000000}]).ok
    assert check("Revenue reached 1500000000", ["$1.5 billion"]).ok
    assert not check("Market cap is $2.6 billion.", [{"market_cap": 2500000000}]).ok


# H3 ---------------------------------------- a dot after a dollar is a decimal point, not thousands
def test_sub_unit_prices_keep_their_decimals():
    assert not check("The API costs $1 per call.", ["Pricing: $0.001 per call"]).ok
    assert not check("The dividend is $125", ["$0.125 per share"]).ok
    assert check("$0.125", [{"dividend": 0.125}]).ok
    assert check("Petrol is $3.599 a gallon.", ["Regular: $3.599"]).ok
    assert check("€1.500", ["Fee: 1.500 EUR"]).ok


def test_rupiah_and_dong_group_thousands_with_dots():
    assert check("Rp 50.000", ["50.000 rupiah"]).ok
    assert check("Harganya Rp 50.000.", [{"price_idr": 50000}]).ok
    assert check("Giá 250.000₫", ["250.000 VND"]).ok


# H4 ---------------------------------------------------- North American phones without a cue
def test_dotted_and_spaced_nanp_phones_are_phones():
    assert ("phone", "800.555.0199") in kinds("Support line: 800.555.0199")
    assert ("phone", "212 555 0199") in kinds("Our NYC office: 212 555 0199.")
    assert not check("Office: 212.555.0198", ["Office: 212.555.0199"]).ok
    assert check("Our NYC office: 212 555 0199.", [{"office_phone": "212-555-0199"}]).ok
    assert check("Reach us at 1.212.555.0199 today.", ["(212) 555-0199"]).ok


# H5 / M5 --------------------------------------------- a number before a date doesn't steal it
def test_a_preceding_number_does_not_steal_a_month_first_date():
    table = "   qty          date\n0    3  Oct 26, 2025\n1   12  Nov 02, 2025\n"
    assert check("Shipped Oct 26, 2025 and Nov 02, 2025.", [table]).ok
    assert check("Released October 26 2025.", ["Version 3 October 26 2025 build"]).ok
    assert check("Stock arrives Oct 26, 2025.", ["Rank 3 Oct 26, 2025 restock"]).ok
    assert not check("Delivered 3 Oct 26, 2025.", ["Delivered 3 Oct 2026."]).ok


def test_a_count_after_a_comma_is_not_a_two_digit_year():
    assert check("Attendance was 45 on 3 March and 52 on 4 March.", ["Attendance: 3 March, 45; 4 March, 52."]).ok


# L4 ------------------------------------------------------------------- two-digit years
def test_two_digit_years_pivot_like_posix():
    assert check("Born 3 Oct 85.", ["born 3 October 1985"]).ok
    assert check("Order placed 12-Dec-99.", [{"placed": "1999-12-12"}]).ok
    assert check("Expires 03-OCT-26.", [{"expiry": "2026-10-03"}]).ok


# M1 ------------------------------------------- phone digits match however the store wrote them
def test_phone_digits_match_identifier_and_quantity_evidence():
    assert check("Reach the customer on +60123456789.", [{"wa_id": "60123456789"}]).ok
    assert check("Your WhatsApp ID is 60123456789.", [{"wa_id": "+60123456789"}]).ok
    assert check("Call +60123456789.", [{"phone": 60123456789}]).ok
    assert check("Your order 0123456789 shipped.", [{"order_id": 123456789}]).ok
    assert check("Your order 123456789 shipped.", [{"order_id": "0123456789"}]).ok
    assert not check("Call +60123456780.", [{"wa_id": "60123456789"}]).ok


# M2 ------------------------------------------------------------------- Malay March
def test_malay_mac_is_march_unless_an_apple_noun_follows():
    assert check("Mesyuarat pada 5 Mac.", ["Tarikh mesyuarat: 5 Mac 2026"]).ok
    assert check("Mesyuarat pada 5 Mac.", [{"meeting_date": "2026-03-05"}]).ok
    assert check("Mesyuarat pada 15 Mac.", ["15 March 2026"]).ok
    assert check("The meeting is on 15 March.", ["Tarikh: 15 Mac"]).ok
    assert check("We supplied 5 Mac laptops to the office.", ["The office received 5 laptops."]).ok


# M3 ------------------------------------------------------------ Malay nights and midnight
def test_malam_is_a_time_only_with_minutes_or_a_clock_word():
    assert check("Pakej 3 hari 2 malam ke Langkawi.", [{"days": 3, "nights": 2}]).ok
    assert check("Menginap 4 malam di hotel.", ["Stay: 4 nights"]).ok
    assert not check("Kedai tutup pukul 12 malam.", ["Lunch break at 12 pm."]).ok
    assert check("Kedai tutup pukul 12 malam.", ["Closes at midnight."]).ok
    assert check("Kedai tutup pukul 10 malam.", ["Closes 10 PM"]).ok
    assert check("Kedai buka 8.30 pagi.", ["Opens 8:30 AM"]).ok


# M4 ---------------------------------------------------------------- suffix ranges
def test_suffixed_amount_ranges_keep_both_magnitudes():
    assert check("Budget is $5K-$10K.", ["Budget between $5,000 and $10,000."]).ok
    assert check("We quoted RM3k-RM5k.", ["RM3,000 to RM5,000"]).ok
    assert check("Grab the RM20 T-shirt today!", [{"item": "T-shirt", "price": 20}]).ok


# M6 -------------------------------------------- spoken years and names are not two numbers
def test_juxtaposed_number_words_are_not_split_into_claims():
    assert check("She was born in nineteen ninety nine.", ["Born 1999."]).ok
    assert check("It all began in twenty twenty.", ["founded in 2020"]).ok
    assert check("We met at Seven Eleven.", ["7-Eleven"]).ok
    assert [c.text for c in check("between fifteen and twenty clinics", []).claims] == ["fifteen", "twenty"]
    assert check("It costs $16 a glass.", ["Who serves a sixteen dollar glass of wine?"]).ok
    assert check("a 2-kilometer run", ["The track features a two-kilometer run"]).ok


# M7 ------------------------------------------------------------- country-code domains
def test_second_level_country_domains_and_joined_sentences():
    assert ("url", "example.com.au") in kinds("Visit example.com.au for details")
    assert not check("Log in at fakebank.com.au", ["Log in at realbank.com.au"]).ok
    assert check("See foo.co.jp", ["foo.co.jp/about"]).ok
    assert check("Go to HP.com for drivers.", ["Go to HP.com.Click Support"]).ok


# L1 -------------------------------------------------------------- Chinese clock times
def test_chinese_clock_times_are_times_not_decimals():
    assert check("我们十一点五十分出发。", ["出发时间：11:50"]).ok
    assert not check("我们十一点五十分出发。", ["出发时间：11:05"]).ok
    assert check("三点半开会", ["Meeting 3:30 PM"]).ok
    assert check("融资一点五亿美元", ["融资1.5亿美元"]).ok
    assert check("11点50分出发", ["出发时间：11:50"]).ok
    extract("1五点半 二3点十分")  # digits and numerals mixed in one hour: not a clock time, and no crash


# L2 ------------------------------------------------------------------ signed deltas
def test_a_signed_count_is_not_a_phone():
    assert check("Views: +12500000 this month.", ["Views grew by 12,500,000"]).ok


# L3 ------------------------------------------------------- IDs are strings, not numbers
def test_leading_zeros_distinguish_codes():
    assert not check("Order #00123 shipped.", ["Order #123 shipped."]).ok
    assert not check("Tracking 0001234567890.", ["Tracking 1234567890"]).ok
    assert check("Order #48213 shipped.", [{"order": 48213}]).ok


# A5 (rest) -------------------------------------- dot-grouped money after a cue is still money
def test_currency_amounts_after_a_cue_word_are_not_phones():
    for text in ("Hubungi kami: Rp 1.500.000 sahaja.", "Call now for $1.500.000 deals."):
        assert "phone" not in [k for k, _ in kinds(text)]


# Port parity (docs/reviews/2026-09-26-deep-check.md, round 2) ----------------------------
def test_only_ascii_digits_after_a_long_number_make_it_a_decimal():
    assert ("identifier", "1234567890") in kinds("ref 1234567890.৫")


def test_deeply_nested_sources_render_without_recursion_limits():
    deep = 12
    for _ in range(3000):
        deep = [deep]
    assert check("Level 12.", [deep]).ok


def test_json_output_escapes_lone_surrogates(tmp_path, capsys):
    import json

    from hardfacts.cli import main

    (tmp_path / "out.txt").write_text("Refund RM 45.", encoding="utf-8")
    (tmp_path / "src.json").write_text('{"note": "\\udc00", "refund": 45}', encoding="utf-8")
    assert main(["check", str(tmp_path / "out.txt"), str(tmp_path / "src.json"), "--json"]) == 0
    printed = capsys.readouterr().out
    assert "\\udc00" in printed and json.loads(printed)["sources"][0].startswith('{"note": "\udc00"')


def test_port_parity_edge_cases():
    # recorded into the conformance fixture, so the TypeScript port must agree on each
    assert check("Call us today 📞📞: 123 4567", ["Call us today: 123 4567"]).ok  # the cue window counts characters
    assert not check("one hundred hundred trillion and one", ["10000000000000000"]).ok  # exact beyond 2^53
    assert [c.kind for c in check("ref 1234567890.৫", []).claims] == ["identifier"]
    assert [c.text for c in check("a\udc00twenty one", []).claims] == ["twenty one"]
