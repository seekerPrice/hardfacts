"""Sources that went through a word tokenizer ("July 22 , 1947") read like normal text.

Found in error analysis of the FaithBench run (bench/results/faithbench-e93d226.json),
so FaithBench numbers after this fix are no longer out-of-sample.
"""

from hardfacts import check


def test_a_space_before_the_comma_does_not_detach_the_year():
    report = check("Albert Brooks was born on July 22, 1947.", ["Albert Brooks ( born Albert Einstein ; July 22 , 1947 ) is an actor ."])

    assert report.ok


def test_tokenised_month_year_and_day_first_dates():
    report = check("It aired from October 3, 2013 to 18 July 2015.", ["aired from October 3 , 2013 to 18 July , 2015 ."])

    assert report.ok
