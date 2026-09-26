from hardfacts import check, feedback

ORDER = {"order_id": "ORD-2024-0012", "tracking": "1Z999AA10123456784", "eta": "2026-10-03"}


def test_feedback_is_empty_when_everything_is_supported():
    assert feedback(check("Tracking: 1Z999AA10123456784.", [ORDER])) == ""


def test_feedback_names_each_unsupported_claim_and_asks_for_a_rewrite():
    report = check("Tracking 1Z999AA10123456785 arrives October 4.", [ORDER])

    text = feedback(report)

    assert '"1Z999AA10123456785"' in text
    assert '"October 4"' in text
    assert "only" in text.lower() and "sources" in text.lower()


def test_kinds_restricts_which_claims_are_checked():
    report = check("Tracking 1Z999AA10123456785 arrives in 3 days.", [ORDER], kinds={"identifier"})

    assert [c.kind for c in report.claims] == ["identifier"]


KETTLE = [{"current": {"price": 94.8}, "new": {"price": 101.12}}]


def test_feedback_shows_the_working_of_a_derived_value_instead_of_asking_to_drop_it():
    text = feedback(check("It's $101.12 and yours was $94.80, so you pay $6.32 more.", KETTLE))
    assert '"$6.32" (amount, which you computed as $101.12 − $94.80' in text
    assert "calculation" in text.lower()


def test_unexplained_lists_only_the_values_no_arithmetic_explains():
    report = check("It's $101.12 and yours was $94.80, so you pay $6.32 more, on card ending 2692.",
                   KETTLE + [{"card": "gift_card_7250692"}])
    assert [c.text for c in report.unsupported] == ["$6.32", "2692"]
    assert [c.text for c in report.unexplained] == ["2692"]
