from hardfacts import check


def test_a_temperature_restated_in_the_same_scale_is_supported():
    report = check("Preheat the oven to 400°F.", ["Preheat oven to 400 degrees F."])

    assert report.ok
    assert [c.kind for c in report.claims] == ["temperature"]


def test_a_conversion_the_model_added_is_a_derived_value_and_unsupported():
    report = check("Preheat the oven to 400°F (200°C).", ["Preheat oven to 400 degrees F."])

    assert [c.text for c in report.unsupported] == ["200°C"]


def test_the_same_number_in_the_other_scale_is_unsupported():
    report = check("Bake at 180°C.", ["Bake at 180°F."])

    assert [c.text for c in report.unsupported] == ["180°C"]


def test_a_range_gives_its_scale_to_both_ends():
    report = check("Heat to 245-250°C.", ["Soft ball: 245-250°F."])

    assert [c.text for c in report.unsupported] == ["245", "250°C"]


def test_a_temperature_is_supported_by_the_same_number_with_its_scale_unstated():
    report = check("The low is 20°F.", ["Low of 20 degrees overnight."])

    assert report.ok


def test_a_bare_number_is_supported_by_a_temperature_with_that_value():
    report = check("It reaches 74 at noon.", ["High: 74°F at noon."])

    assert report.ok


def test_a_scale_letter_attached_to_the_number_is_a_temperature():
    report = check("Preheat the oven to 250°F, or 180°C for fish.", ["PREHEAT oven to 250F. Fish: 180C."])

    assert report.ok
