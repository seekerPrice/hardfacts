"""Bahasa Melayu / Indonesia and 中文 Hard facts, alone and code-switched."""

from hardfacts import check

ORDER = {"order_id": "ORD-2024-0012", "refund": 1200, "currency": "MYR", "refund_days": 5}


# ----------------------------------------------------------------------- Bahasa Melayu


def test_malay_reply_with_an_invented_refund_window_is_flagged():
    report = check("Bayaran balik RM1,200 akan dikreditkan dalam 7 hari bekerja.", [ORDER])

    assert [c.text for c in report.unsupported] == ["7"]
    assert report.claims[0].kind == "money"


def test_malay_number_words_are_values():
    report = check("Seramai dua ratus lima puluh peserta dan sepuluh ribu penonton.", ["250 participants, 10,000 viewers"])

    assert report.ok
    assert [c.value for c in report.claims] == [250, 10000]


def test_malay_teens_and_tens():
    report = check("Lapan belas pelajar dan dua puluh satu guru.", ["18 students and 21 teachers"])

    assert report.ok


def test_malay_magnitudes_and_percent():
    report = check("Jualan RM1.2 juta, naik 15 peratus.", ["Sales: MYR 1,200,000 (up 15%)"])

    assert report.ok


def test_malay_months():
    report = check("Dihantar pada 16 Januari 2022, dijangka tiba Ogos 2022.", [{"shipped": "2022-01-16", "eta": "2022-08-03"}])

    assert report.ok


def test_small_malay_counts_are_not_claims():
    report = check("Dua orang pegawai akan menghubungi anda.", ["An officer will contact you."])

    assert report.claims == ()


# --------------------------------------------------------------------------------- 中文


def test_chinese_reply_with_an_invented_refund_window_is_flagged():
    report = check("退款1200元将在3个工作日内到账。", [ORDER])

    assert [c.text for c in report.unsupported] == ["3"]


def test_chinese_numerals_and_scales_are_values():
    report = check("共有三千五百人参加，另有1.2万人在线观看，预算3亿。", ["3,500 attended; 12,000 watched online; budget 300 million"])

    assert report.ok
    assert [c.value for c in report.claims] == [3500, 12000, 300000000]


def test_chinese_numerals_with_zero_and_liang():
    report = check("两百零五个座位，一万零五百张票。", ["205 seats and 10,500 tickets"])

    assert report.ok


def test_chinese_percent():
    report = check("增长了百分之十五，利润率12.5%。", ["Growth 15 percent; margin 12.5%"])

    assert report.ok
    assert [c.kind for c in report.claims] == ["percent", "percent"]


def test_chinese_dates():
    report = check("订单于2022年1月16日发出，预计3月2日送达。", [{"shipped": "2022-01-16", "eta": "2022-03-02"}])

    assert report.ok
    assert [c.kind for c in report.claims] == ["date", "date"]


def test_chinese_idioms_with_numerals_are_not_claims():
    report = check("我们十分重视，万一有问题请一起联系第一线客服。", ["Contact support."])

    assert report.claims == ()


# ------------------------------------------------------------------------ code-switched


def test_manglish_code_switched_reply():
    report = check("Boss, your order ORD-2024-0012 refund RM1.2k, 5 hari bekerja ya. 谢谢!", [ORDER])

    assert report.ok


# Found by a 90-case BM / Manglish / 中文 support corpus (model-written, not native-checked).
def test_malay_day_parts_pagi_and_petang_are_times_malam_needs_a_cue():
    assert check("Buka 9 pagi hingga 6 petang, Sabtu 9 pagi hingga 1 petang.", ["Mon-Fri 09:00-18:00, Sat 09:00-13:00"]).ok
    assert check("Slot 2 ptg - 6 ptg.", ["slot 14:00-18:00"]).ok
    assert check("Daftar keluar jam 12 tengah hari.", [{"check_out": "2026-11-22T12:00:00+08:00"}]).ok
    assert check("Pakej 3 hari 2 malam.", [{"days": 3, "nights": 2}]).ok
    assert not check("Kedai tutup 5 petang.", ["Closes 15:00"]).ok


def test_malay_month_abbreviations():
    assert check("Hantar pada 1hb Okt.", [{"delivery_date": "2026-10-01"}]).ok
    assert check("Temujanji 6 Dis 2026.", [{"date": "2026-12-06"}]).ok


def test_a_time_after_a_date_is_not_a_two_digit_year():
    assert check("Your bus is 10 Oct 11.30pm from TBS.", [{"departure": "2026-10-10T23:30:00+08:00"}]).ok
    assert not check("Your bus is 10 Oct 11.30am from TBS.", [{"departure": "2026-10-10T23:30:00+08:00"}]).ok


def test_chinese_times_with_a_day_part():
    assert check("预约时间是上午11点。", [{"time": "11:00"}]).ok
    assert check("营业时间上午9点至下午6点。", ["09:00-18:00"]).ok
    assert not check("预约在下午3点。", [{"time": "3:00 AM"}]).ok
    assert not check("晚上8点见。", [{"time": "19:00"}]).ok


def test_chinese_and_malay_phone_cues():
    assert check("您的电话号码8123 4567本月账单已出。", [{"msisdn": "+6581234567"}]).ok
    assert not check("您的电话号码8123 4568本月账单已出。", [{"msisdn": "+6581234567"}]).ok


# SEA probe (bench/sea_probe.py), 2026-09-27.
def test_colloquial_chinese_kuai_with_a_trailing_digit_is_tenths():
    assert check("运费是八块五。", [{"shipping_fee": 8.50}]).ok
    assert check("运费是8块5。", [{"shipping_fee": 8.50}]).ok
    assert not check("运费是九块五。", [{"shipping_fee": 8.50}]).ok
    assert check("一共十二块。", [{"total": 12}]).ok


def test_an_ambiguous_day_month_after_a_delivery_word_is_a_date_with_both_readings():
    source = [{"eta": "2026-10-03"}]
    assert check("Order confirm arrive 3/10.", source).ok  # Malaysian day/month
    assert check("Delivery on 10/3.", source).ok  # US month/day
    assert not check("Order confirm arrive 4/10.", source).ok
    assert ("date", "1/2") not in [(c.kind, c.text) for c in check("Add 1/2 cup.", []).claims]
    assert [c.kind for c in check("Rated on 9/0 scale.", []).claims] == ["quantity", "quantity"]  # no day 0
    for fraction in ("After 1/2 hour, turn it down.", "Add 1/2 cup and 1/4 cup of cheese.", "About 1/2 inch to 1 inch wide."):
        assert "date" not in [c.kind for c in check(fraction, []).claims], fraction


def test_a_malay_amount_in_words_with_sen_is_one_amount():
    source = [{"total": 149.90}]
    assert check("Jumlahnya seratus empat puluh sembilan ringgit sembilan puluh sen.", source).ok
    assert not check("Jumlahnya seratus lima puluh sembilan ringgit sembilan puluh sen.", source).ok
    assert check("It comes to one hundred forty-nine dollars and ninety cents.", source).ok
