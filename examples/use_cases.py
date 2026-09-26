"""The five use cases on examples/use-cases.html, run through hardfacts: uv run python examples/use_cases.py"""
import json
from hardfacts import check

cases = {
    "whatsapp": (
        "Hi Aina! Your order ORD-2024-0012 ships via Pos Laju. Tracking: EN123456780MY, arriving 2 October. Shipping was RM 12.90.",
        [{"order_id": "ORD-2024-0012", "carrier": "Pos Laju", "tracking": "EN123456789MY", "eta": "2026-10-03", "shipping_fee": 12.90}],
    ),
    "refund": (
        "Your new fare is $101.12 and you paid $94.80, so the difference of $6.32 will be charged to your card ending in 1784.",
        [{"new_fare": 101.12, "paid": 94.80, "payment_method_id": "credit_card_9921784"}],
    ),
    "policy": (
        "Full-time staff get 16 days of annual leave, and unused leave expires on 31 March 2027. Claims above RM 500 need HR approval.",
        ["Annual leave: full-time employees are entitled to 14 days per year. Unused leave may be carried forward until 31 March 2027. Expense claims above RM 500 require approval from HR."],
    ),
    "agent": (
        "Done: PR #3337 is merged, all 251 tests pass, and the build finished in 42 s.",
        ["$ gh pr view 3337 --json state\n{\"state\": \"MERGED\"}", "$ pytest -q\n249 passed, 2 failed in 4.21s", "$ npm run build\nBuilt in 41.8s"],
    ),
    "kol": (
        "Top pick: @makan.with.mei, 128K followers, 4.2% engagement, quoting RM 3,500 per Reel. Her last campaign drove 1,240 sign-ups.",
        [{"handle": "@makan.with.mei", "followers": 128000, "engagement_rate": 0.042, "rate_card": {"reel": 3500}, "past_campaigns": [{"signups": 1204}]}],
    ),
}
out = {}
for k, (o, s) in cases.items():
    r = check(o, s).to_dict()
    out[k] = [(c["kind"], c["text"], c["supported"], (c["derivation"] or {}).get("expression")) for c in r["claims"]]
    print(k, json.dumps(out[k], ensure_ascii=False))
