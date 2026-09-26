"""Derivations: arithmetic over the Output's own Supported values that explains an Unsupported one (ADR-0007)."""

from hardfacts import check

PRICES = [{"current": {"price": 94.8}, "new": {"price": 101.12}}]


def unsupported(report):
    return [(c.text, c.derivation.expression if c.derivation else None) for c in report.unsupported]


def test_a_difference_of_two_stated_values_is_explained_but_stays_unsupported():
    report = check("The new kettle is $101.12 and yours was $94.80, so you pay $6.32 more.", PRICES)
    assert not report.ok
    assert unsupported(report) == [("$6.32", "$101.12 − $94.80")]


def test_the_derivation_points_at_its_operands():
    output = "The new kettle is $101.12 and yours was $94.80, so you pay $6.32 more."
    d = check(output, PRICES).unsupported[0].derivation
    assert [output[a:b] for a, b in d.operands] == ["$101.12", "$94.80"]


def test_a_total_of_stated_values_is_explained():
    fares = [{"flights": [{"price": 123}, {"price": 167}]}]
    report = check("Fares: $123 and $167, total $290.", fares)
    assert unsupported(report) == [("$290", "$123 + $167")]


def test_a_multiple_by_a_stated_count_is_explained():
    report = check("The fare is $174 per person for 2 passengers: $348 in all.", [{"price": 174, "passengers": 2}])
    assert unsupported(report) == [("$348", "$174 × 2")]


def test_wrong_arithmetic_or_an_invented_value_has_no_derivation():
    report = check("The new kettle is $101.12 and yours was $94.80, so you pay $235.94 more.", PRICES)
    assert unsupported(report) == [("$235.94", None)]


def test_operands_must_be_supported():
    # $6 is itself Unsupported, so it can't explain $56 = $50 + $6 (nor can $56 explain $6)
    assert unsupported(check("It costs $50 plus $6, so $56.", [{"base": 50}])) == [("$6", None), ("$56", None)]


def test_operands_must_be_of_the_same_kind():
    # 6% is a percentage, not an amount
    assert unsupported(check("It costs $50 plus 6%, so $56.", [{"base": 50, "tax_percent": 6}])) == [("$56", None)]


def test_the_report_dict_carries_the_derivation():
    d = check("The new kettle is $101.12 and yours was $94.80, so you pay $6.32 more.", PRICES).to_dict()
    assert d["unsupported"][0]["derivation"] == {"expression": "$101.12 − $94.80", "operands": [[18, 25], [40, 46]]}
    assert [c["derivation"] for c in d["claims"]][:2] == [None, None]


def test_a_reply_with_many_amounts_is_still_fast():
    import random
    import time

    rng = random.Random(0)
    prices = [round(rng.uniform(10, 999), 2) for _ in range(60)]
    output = " ".join(f"${p:.2f}" for p in prices) + " " + " ".join(f"${rng.uniform(10, 999):.3f}" for _ in range(30))
    t0 = time.perf_counter()
    check(output, [{"prices": prices}])
    assert time.perf_counter() - t0 < 0.1


# Ratios and percentage changes, for a percentage stated to a decimal (bench/ratio_experiment.py --strict).
def test_a_percentage_change_between_the_replys_own_values_shows_its_working():
    report = check("The value rose from 100.00 to 137.90, a return of 37.9%.", ["The index was 100.00 on 1/2/2010 and 137.90 on 1/1/2011."])
    claim = next(c for c in report.claims if c.text == "37.9%")
    assert not claim.supported and claim.derivation.expression == "(137.90 − 100.00) ÷ 100.00 × 100"
    assert not report.unexplained


def test_a_share_shows_its_working():
    report = check("Of 250 orders, 87 were late: 34.8%.", ["250 orders, 87 late"])
    claim = next(c for c in report.claims if c.text == "34.8%")
    assert claim.derivation.expression == "87 ÷ 250 × 100"


def test_a_whole_percentage_is_not_searched_for_ratios():
    report = check("Of 250 orders, 87 were late: 35%.", ["250 orders, 87 late"])
    assert next(c for c in report.claims if c.text == "35%").derivation is None


def test_a_wrong_percentage_gets_no_ratio_working():
    report = check("Of 250 orders, 87 were late: 38.4%.", ["250 orders, 87 late"])
    assert next(c for c in report.claims if c.text == "38.4%").derivation is None
