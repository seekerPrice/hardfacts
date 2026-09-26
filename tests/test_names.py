"""Names with digits are checked against same-shaped names in the Sources (ADR-0008)."""

from hardfacts import check


def _claims(output, sources):
    return [(c.kind, c.text, c.supported) for c in check(output, sources).claims]


def test_a_digit_changed_inside_a_name_is_unsupported_when_the_source_names_its_sibling():
    source = ["COVID-19 is caused by SARS-CoV-2."]
    assert ("name", "COVID-12", False) in _claims("COVID-12 is caused by a coronavirus.", source)
    assert not check("The H2N1 campaign ran in 2009.", ["The H1N1 campaign ran in 2009."]).ok
    assert not check("File a Schedule 16G.", ["File a Schedule 13G."]).ok
    assert not check("CD6 T-cell responses rose.", ["CD8 T-cell responses rose."]).ok


def test_the_same_name_is_supported_ignoring_case_and_hyphens():
    assert check("COVID-19 spread quickly.", ["covid19 spread quickly."]).ok
    assert ("name", "COVID-19", True) in _claims("COVID-19 spread quickly.", ["COVID-19 spread"])


def test_a_name_with_no_sibling_in_the_sources_is_not_a_claim():
    assert _claims("Take vitamin B12 daily.", ["Take vitamins daily."]) == []
    assert check("Take vitamin B12 daily.", ["Take vitamins daily."]).ok


def test_values_and_currency_amounts_are_not_names():
    assert [k for k, _, _ in _claims("It costs RMB105.", ["It costs RMB1."])] == ["money"]
    assert ("name", "5-year", False) not in _claims("A 5-year plan.", ["A 3-year plan."])


def test_names_can_be_left_out_with_kinds():
    assert check("COVID-12 spread.", ["COVID-19 spread."], kinds={"quantity"}).ok
    assert not check("COVID-12 spread.", ["COVID-19 spread."], kinds={"name"}).ok


# Round 9 of hostile review.
def test_a_hyphen_between_digits_is_kept():
    assert ("name", "X1-2", True) not in _claims("X1-2 is here", ["X12 here"])
    assert ("name", "1-2A", True) not in _claims("Model 1-2A", ["Model 12A"])


def test_full_width_digits_are_read_as_their_ascii_digits():
    assert not check("COVID-１９ spread.", ["COVID-18 spread."]).ok
    assert check("COVID-１９ spread.", ["COVID-19 spread."]).ok


def test_many_names_are_checked_in_linear_time():
    import time
    output = " ".join(f"x{i}" for i in range(20000))
    start = time.perf_counter()
    check(output, ["x1"])
    assert time.perf_counter() - start < 2.0
