from hardfacts import check


def test_digits_are_supported_by_number_words_in_the_source():
    report = check("11 victims: 8 men and 3 women.", ["11 victims -- eight men and three women -- have been identified"])

    assert report.ok


def test_a_changed_count_is_unsupported_even_when_the_source_spells_it_out():
    report = check("The blast injured 5 people.", ["Six people were injured in the blast."])

    assert [c.text for c in report.unsupported] == ["5"]


def test_number_words_in_the_output_are_claims():
    report = check("Seventy years ago, twenty-one people and two hundred and fifty soldiers left.", [
        "70 years ago 21 people and 250 soldiers left."
    ])

    assert report.ok
    assert [c.value for c in report.claims] == [70, 21, 250]


def test_a_spelled_out_number_not_in_the_source_is_unsupported():
    report = check("The rescue took twelve hours.", ["The rescue took five hours."])

    assert [c.text for c in report.unsupported] == ["twelve"]


def test_spelled_out_numbers_below_ten_are_not_claims():
    # Style guides spell out small counts, and they are usually derived ("the two men").
    report = check("The two leaders met three times.", ["Leaders Ali and Chen met on 3 May, 9 May and 1 June."])

    assert report.claims == ()


def test_spelled_out_numbers_below_ten_are_still_evidence():
    report = check("3 women were among the victims.", ["Victims included three women."])

    assert report.ok


def test_every_day_idioms_are_not_claims():
    report = check("Open seven days a week and 24/7 online, 24 hours a day.", [{"hours": {"Monday": "9:0-17:0"}}])

    assert report.claims == ()


def test_a_dozen_and_a_hundred_are_numbers():
    report = check("About a dozen eggs and a hundred guests.", ["12 eggs, 100 guests"])

    assert report.ok


def test_the_word_one_on_its_own_is_not_a_claim():
    report = check("She is one of the best players and one who never quits.", ["She is a top player."])

    assert report.claims == ()


def test_a_scale_word_on_its_own_is_not_a_number():
    report = check("The Million Man March drew thousands.", ["A march in Washington."])

    assert report.claims == ()
