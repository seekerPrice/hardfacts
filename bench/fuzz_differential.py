"""Fuzz the TypeScript port against the Python reference with generated text.

    uv run python bench/fuzz_differential.py --cases 20000

Texts are drawn from an alphabet dense in what hardfacts reads: digits, separators,
currency symbols, clock and date words, English, Malay and Chinese number words, plus
characters outside the BMP. Both implementations must return the same rendered Sources,
Claims, texts, verdicts, Values, spans and Evidence (TS offsets are UTF-16 units, converted
to code points).

Structured Sources include whole floats (12.0) and integer-like keys ("0", "1355937109"),
which JSON.parse turns into 12 and moves to the front: both ports render them that way.
"""

from __future__ import annotations

import argparse
import json
import random
import subprocess
import sys
from pathlib import Path

from hardfacts import check
from hardfacts._extract import EXACT

ROOT = Path(__file__).resolve().parent.parent
TOKENS = (list("0123456789") * 6 + list(" .,:;-/$%°#@()+'\"\n") * 2 + list("年月日元万亿三十百千两零第") + [
    " ", " ", " ", "RM", "US$", "S$", "€", "£", "¥", "k", "K", "M", "B", "bn", "am", "pm", "a.m.", "PM", "C", "F", "°F",
    "May ", "Jan ", "March ", "Julai ", "Ogos ", "th", "st", " , ", " percent", " peratus", "百分之", "twenty", "one ",
    "hundred ", "a dozen ", "million", "juta", "ribu", "dua ", "ratus ", "lima ", "puluh ", "sebelas ", "noon", "midnight",
    "ORD-", "EN", "MY", "#", "@shop.com", "https://ex.com/", "www.", "step ", "Passage ", "out of ", " words", "24/7",
    "\\n", "\\xa0", "&#160;", "½", "COVID-", "-year-old", "x", "–", " to ",
    "\u00a0", "\u202f", "\u3000", "１", "２", "０", "％", "：", "٤", "T", "+08:00", "Z", "Rp ", ".000", " pagi", " petang",
    "call ", "hotline ", "+60", "0", "-shirt", "万", ",000", "十分", "千万", "−",
    "16:9", "Oct ", "Oktober ", "hb ", "点", "五", "亿", " and ", "fifteen ", "first ", "-Oct-", "Mac ", ".com", "a.",
    "😀", "𝐀", "🇲🇾", "\r", "\u2028",
    " malam", "pukul ", "jam ", "₫", ".555.", "0199", "-$", "K-", "k-RM", ".com.au", ".co.jp", ".Click", "点半", "分", "一刻",
    "nineteen ", "ninety ", "a ", "an ", "Seven ", "+1", "laptops", " 85", "-Dec-", "USD", "IDR", "rupiah",
    "9999999", "0000000", "credit_card_", "_", "19th and ", "th", "XEHM8B", "2024-05-15 ", "May 23rd",
    "card ending in ", "ending ", "last four digits ", "****", "xxxx", "••••", "gift_card_",
    "**", "***", "•", "·", " ends in ", "plan ", "current time is ", "now: ", " place", "reservation ", "LLAMA3",
    "https://gh.com/o/r/pull/", "`", "33e41b9", "33e41b9670c2", "#33", "/issues/",
    " ptg", " tengah hari", "上午", "下午", "晚上", "电话", " Okt ", " Dis ", "11.30", "hb ",
])


def text(rng: random.Random) -> str:
    return "".join(rng.choice(TOKENS) for _ in range(rng.randint(0, 60)))


def arithmetic(rng: random.Random) -> dict:
    """A reply listing many supported amounts and some sums of them: the Derivation search's worst case.
    Operand counts straddle its thresholds (16 and 60)."""
    n = rng.choice([2, 3, 5, 8, 15, 16, 17, 30, 59, 60, 61, 80])
    pool = [rng.choice([rng.randint(1, 60), round(rng.uniform(1, 300), 2), rng.randint(1, 9)]) for _ in range(n)]
    targets = [round(sum(rng.sample(pool, rng.randint(2, min(5, n)))), 2) if rng.random() < 0.5 else rng.randint(1, 400)
               for _ in range(3)]
    cur = rng.choice(["$", "RM", "€", ""])
    return {"output": " , ".join(f"{cur}{v}" if cur else f"{v} items" for v in pool + targets), "sources": [{"v": pool}]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=int, default=20000)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    cases = []
    for i in range(args.cases):
        if rng.random() < 0.1:
            cases.append({"id": i, **arithmetic(rng)})
            continue
        output = text(rng)
        sources = [output if rng.random() < 0.3 else text(rng) for _ in range(rng.randint(0, 2))]
        if rng.random() < 0.2:
            sources.append({"n": rng.randint(0, 10**12), "t": text(rng), "f": rng.randint(0, 9999) + rng.choice([0.0, 0.25, 0.5, 0.05]),
                            str(rng.randint(0, 5 * 10**9)): text(rng), "0": rng.choice([-0.0, 1e16, 2.0])})
        cases.append({"id": i, "output": output, "sources": sources})
    bad = compare(cases)
    print(f"{args.cases - bad}/{args.cases} identical")
    return 1 if bad else 0


def compare(cases: list[dict]) -> int:
    """Run every case through both ports; print the first few differences and return how many differ.

    Compared: the rendered Sources, and per Claim its Kind, text, verdict, Value, span, Evidence
    and Derivation (spans in code points on both sides)."""
    ts = subprocess.run(["node", str(ROOT / "ts/bench/check-jsonl.ts")], input="\n".join(json.dumps(c, ensure_ascii=False) for c in cases),
                        capture_output=True, text=True, check=True)
    got = {row["id"]: [row["sources"], row["claims"]] for row in map(json.loads, filter(None, ts.stdout.split("\n")))}
    bad = 0
    for c in cases:
        report = check(c["output"], c["sources"])
        claims = [[x.kind, x.text, x.supported, x.value, list(x.span), [[e.source, list(e.span), e.text] for e in x.evidence],
                   None if x.derivation is None else [x.derivation.expression, [list(o) for o in x.derivation.operands]]]
                  for x in report.claims]
        py = json.loads(json.dumps([list(report.sources), claims], ensure_ascii=False,
                                   default=lambda d: format(d.normalize(EXACT), "f")))
        if py != got[c["id"]]:
            bad += 1
            if bad <= 5:
                print(json.dumps({"output": c["output"], "sources": c["sources"], "py": py, "ts": got[c["id"]]}, ensure_ascii=False)[:800])
    return bad


if __name__ == "__main__":
    sys.exit(main())
