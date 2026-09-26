from hardfacts import check

ORDER = {"order_id": "ORD-2024-0012", "tracking": "1Z999AA10123456784", "carrier": "UPS"}


def test_an_invented_tracking_number_is_unsupported():
    report = check("Your parcel's tracking number is 1Z999AA10123456785.", [ORDER])

    assert [(c.kind, c.text) for c in report.unsupported] == [("identifier", "1Z999AA10123456785")]


def test_identifiers_match_ignoring_case_and_separators():
    report = check("Order ord-2024-0012 (ORD20240012) ships via UPS as 1z999aa10123456784.", [ORDER])

    assert report.ok


def test_an_identifier_is_not_supported_by_part_of_a_longer_one():
    report = check("Reference AB123.", ["Reference XAB1234."])

    assert [c.text for c in report.unsupported] == ["AB123"]


def test_units_ordinals_and_decades_are_not_identifiers():
    report = check("It weighs 5kg, ranked 2nd since the 1990s.", ["5 kg, placed 2nd, since the 1990s"])

    assert "identifier" not in {c.kind for c in report.claims}
    assert report.ok


def test_phone_numbers_match_in_any_format():
    report = check("Call (510) 889-8690 or +60 12-345 6789.", ["Hayward: 510-889-8690. KL office: 012-3456789"])

    assert report.ok
    assert [c.kind for c in report.claims] == ["phone", "phone"]


def test_an_invented_phone_number_is_unsupported():
    report = check("Call us at 1-800-555-0199.", ["Support line: 1-800-555-0100"])

    assert [c.text for c in report.unsupported] == ["1-800-555-0199"]


def test_year_ranges_are_not_phone_numbers():
    report = check("Between 1990-1995 sales rose.", ["Sales rose from 1990 to 1995."])

    assert report.ok


def test_emails_match_case_insensitively_and_invented_ones_are_unsupported():
    report = check("Email Support@Shop.com or refunds@shop.com.", ["Contact support@shop.com"])

    assert [(c.kind, c.text) for c in report.unsupported] == [("email", "refunds@shop.com")]


def test_a_url_is_supported_by_the_same_page_or_a_deeper_one():
    report = check("Track it at https://www.ups.com/track or see ups.com.", [
        "Tracking page: https://ups.com/track/?loc=en_US"
    ])

    assert report.ok


def test_an_invented_url_path_is_unsupported():
    report = check("Download the form at https://shop.com/forms/refund.pdf.", ["Forms live at https://shop.com/help"])

    assert [c.text for c in report.unsupported] == ["https://shop.com/forms/refund.pdf"]


def test_number_word_compounds_are_quantities_not_identifiers():
    report = check("A 73-year-old deputy at a 4.5-star diner.", ["Bates, 73, a deputy; business_stars: 4.5"])

    assert [(c.kind, c.value) for c in report.claims] == [("quantity", 73), ("quantity", 4.5)]
    assert report.ok


def test_short_names_with_digits_are_not_claims():
    report = check("During COVID-19 they sold B12 shots at 7-Eleven.", ["They sold vitamin shots at a convenience store."])

    assert report.claims == ()


def test_html_entities_are_not_claims():
    report = check("monarchs.&#160;The author argues", ["monarchs. The author argues"])

    assert report.claims == ()


def test_hyphenated_number_ranges_and_decades_are_quantities():
    report = check("Muscle burns 6-to-12 calories; styles from the mid-1800s and 1940s-style diners.", [
        "burns about 6 to 12 calories. Popular since 1800, revived 1940."
    ])

    assert "identifier" not in {c.kind for c in report.claims}


def test_a_missing_space_after_a_full_stop_does_not_hide_a_number():
    report = check("Pick numbers from 1 to 49.", ["numbers from 1 to 49.Not as simple as it sounds"])

    assert report.ok


def test_six_character_booking_codes_are_identifiers():
    # airline record locators: six uppercase letters and digits, often only one digit (tau-bench audit)
    booking = [{"reservation_id": "XEHM8B", "status": "confirmed"}]
    assert check("Your reservation XEHM8B is confirmed.", booking).ok
    assert not check("Your reservation XEHM9B is confirmed.", booking).ok
    assert not check("Your reservation XEHN8B is confirmed.", booking).ok
    assert check("The COVID-19 rules and B12 levels in MP3 form.", []).ok  # short names stay names


# Found by running the Claude Code hook over real sessions (integrations/claude-code/README.md).
def test_markdown_around_a_url_is_not_part_of_it():
    report = check("PR is up: **https://github.com/o/r/pull/637** and `app.vercel.app/tree`.",
                   ["https://github.com/o/r/pull/637", "deployed to app.vercel.app/tree"])
    assert [(c.kind, c.text) for c in report.claims] == [("url", "https://github.com/o/r/pull/637"), ("url", "app.vercel.app/tree")]
    assert report.ok


def test_a_number_in_a_url_path_supports_a_reference_to_it():
    assert check("Opened PR #3337.", ["https://github.com/o/r/pull/3337"]).ok
    assert not check("Opened PR #3338.", ["https://github.com/o/r/pull/3337"]).ok
    assert not check("It costs $3337.", ["https://github.com/o/r/pull/3337"]).ok


def test_git_hashes_of_any_length_name_one_commit():
    full = "commit 33e41b9670c2f1a5d8e9b0c1d2e3f4a5b6c7d8e9"
    assert check("Pushed as `33e41b967`.", [full]).ok
    assert not check("Pushed as 33e41b9670c2f1a5d8e9b0c1d2e3f4a5b6c7d8e9.", ["[main 33e41b9] fix"]).ok  # longer: more specific
    assert not check("Pushed as `33e41b968`.", [full]).ok
    assert not check("Order ABC1234.", ["Order ABC12345"]).ok  # prefixes count only for hex hashes
    assert not check("Tracking 1234567890.", ["Tracking 12345678901"]).ok  # all-digit IDs stay exact
