from hardfacts import check

HOURS = {"hours": {"Tuesday": "16:30-21:0", "Saturday": "11:0-14:0"}}


def test_twelve_hour_restatements_of_twenty_four_hour_sources_are_supported():
    report = check("Open Tuesdays from 4:30 PM to 9 p.m., Saturdays 11am-2pm.", [HOURS])

    assert report.ok
    assert {c.kind for c in report.claims} == {"time"}


def test_a_closing_time_not_in_any_source_is_unsupported():
    report = check("Open Tuesdays until 10 PM.", [HOURS])

    assert [c.text for c in report.unsupported] == ["10 PM"]


def test_a_time_without_am_or_pm_is_supported_by_either_reading():
    report = check("Doors close at 9:00.", [HOURS])

    assert report.ok


def test_noon_and_midnight_are_times():
    report = check("Lunch service ends at noon; the bar closes at midnight.", ["Lunch: 11:00-12:00. Bar: 18:00-0:00"])

    assert report.ok
    assert [c.kind for c in report.claims] == ["time", "time"]


def test_a_time_is_not_supported_by_the_same_digits_used_as_a_quantity():
    report = check("We open at 9 AM.", ["We have 9 tables."])

    assert [c.text for c in report.unsupported] == ["9 AM"]


def test_a_time_label_followed_by_a_colon_is_still_a_time():
    report = check("At 3am it is 20 degrees.", ["3am:The forecast is 20 degrees."])

    assert report.ok


def test_a_label_colon_before_a_number_does_not_make_a_time():
    report = check("Do not over-shave (Passage 1). By 3pm it clears.", ["passage 1:1 Do not over-shave. passage 3:3pm: Clear."])

    assert report.ok


def test_a_twenty_four_hour_time_with_a_stray_pm_is_still_that_time():
    report = check("Open 11:00 AM to 15:00 PM.", [{"hours": {"Monday": "11:0-15:0"}}])

    assert report.ok
