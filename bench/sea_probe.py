"""Probe: realistic Bahasa Melayu, 中文 and Manglish support replies, each correct and with one planted error.

    uv run python bench/sea_probe.py

Written by a non-native speaker (Claude) as a smoke test, not a validation: the ROADMAP asks for
native-speaker cases. Each case is (source, correct reply, reply with one planted error). The correct
reply should pass and the planted one should be flagged. Every miss is printed with the Report.
"""

from __future__ import annotations

import sys

from hardfacts import check

ORDER = {"order_id": "ORD-88213", "tracking": "EF123456789MY", "eta": "2026-10-03", "total": 149.90,
         "shipping_fee": 8.50, "refund": 12.00, "refund_eta": "3 working days", "hotline": "03-2770 1234", "hours": "9:00-18:00"}

CASES = [
    # Bahasa Melayu
    ("Pesanan ORD-88213 anda akan sampai pada 3 Oktober.", "Pesanan ORD-88213 anda akan sampai pada 4 Oktober."),
    ("Nombor penjejakan anda ialah EF123456789MY.", "Nombor penjejakan anda ialah EF123456780MY."),
    ("Jumlah bayaran ialah RM149.90 termasuk caj penghantaran RM8.50.", "Jumlah bayaran ialah RM149.90 termasuk caj penghantaran RM9.50."),
    ("Bayaran balik sebanyak RM12 akan dikreditkan dalam masa 3 hari bekerja.", "Bayaran balik sebanyak RM21 akan dikreditkan."),
    ("Sila hubungi talian kami di 03-2770 1234.", "Sila hubungi talian kami di 03-2770 1235."),
    ("Kami beroperasi dari 9 pagi hingga 6 petang.", "Kami beroperasi dari 9 pagi hingga 7 petang."),
    ("Jumlahnya seratus empat puluh sembilan ringgit sembilan puluh sen.", "Jumlahnya seratus lima puluh sembilan ringgit sembilan puluh sen."),
    ("Barang dijangka tiba 3hb Oktober 2026.", "Barang dijangka tiba 5hb Oktober 2026."),
    ("Caj penghantaran ialah RM 8.50 sahaja.", "Caj penghantaran ialah RM 5.80 sahaja."),
    ("Pesanan anda bernilai RM149.90.", "Pesanan anda bernilai RM194.90."),
    # 中文
    ("您的订单ORD-88213预计10月3日送达。", "您的订单ORD-88213预计10月5日送达。"),
    ("您的快递单号是EF123456789MY。", "您的快递单号是EF123456789MX。"),
    ("订单总额为RM149.90，运费RM8.50。", "订单总额为RM149.90，运费RM8.80。"),
    ("退款12令吉将在三个工作日内退回。", "退款21令吉将在三个工作日内退回。"),
    ("客服热线：03-2770 1234。", "客服热线：03-2770 4321。"),
    ("我们的营业时间是上午9点到下午6点。", "我们的营业时间是上午9点到下午8点。"),
    ("预计2026年10月3日到货。", "预计2026年10月13日到货。"),
    ("总共一百四十九点九令吉。", "总共一百九十四点九令吉。"),
    ("运费是八块五。", "运费是九块五。"),
    ("您的订单金额是149.90令吉。", "您的订单金额是194.90令吉。"),
    # Manglish / code-switched
    ("Your parcel EF123456789MY sampai 3 Oct, ok?", "Your parcel EF123456789MY sampai 5 Oct, ok?"),
    ("Refund RM12 dah process, 3 working days masuk.", "Refund RM20 dah process, 3 working days masuk."),
    ("Shipping fee RM8.50 only lah, total RM149.90.", "Shipping fee RM8.50 only lah, total RM159.90."),
    ("Call our hotline 03-2770 1234 ya, 9am to 6pm.", "Call our hotline 03-2770 1234 ya, 9am to 10pm."),
    ("Order ORD-88213 confirm arrive 3/10.", "Order ORD-88213 confirm arrive 13/10."),
    ("你的parcel EF123456789MY明天到, total RM149.90.", "你的parcel EF123456789MY明天到, total RM149.00."),
    ("Boss, refund RM12 dah masuk account you.", "Boss, refund RM120 dah masuk account you."),
    ("Delivery on 3 Okt, fee RM8.50.", "Delivery on 3 Okt, fee RM6.50."),
    ("ETA 03/10/2026, tracking EF123456789MY.", "ETA 03/11/2026, tracking EF123456789MY."),
    ("Total RM149.90 (incl. RM8.50 shipping).", "Total RM149.90 (incl. RM8.90 shipping)."),
]


def main() -> int:
    false_alarms = misses = 0
    for correct, planted in CASES:
        good = check(correct, [ORDER])
        bad = check(planted, [ORDER])
        if not good.ok:
            false_alarms += 1
            print("FALSE ALARM:", correct, "→", [(c.kind, c.text) for c in good.unsupported])
        if bad.ok:
            misses += 1
            print("MISSED:     ", planted, "→ claims", [(c.kind, c.text, c.supported) for c in bad.claims])
    print(f"{len(CASES)} cases: {false_alarms} false alarms on correct replies, {misses} planted errors missed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
