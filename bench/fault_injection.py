"""Fault injection: plant one fabricated hard fact in a clean response and see if it is caught.

    uv run python bench/fault_injection.py --split train
    uv run python bench/fault_injection.py --split test --record

Human labels answer "how often is a flag right?". They are a noisy guide to recall,
because annotators miss things and label spans for mixed reasons. Fault injection
answers the recall question the tool is built for, under control:

1. Take RAGTruth responses the annotators judged clean (no hallucination spans).
2. Pick one digit run in the response that also appears in the prompt. The pick uses
   a plain regex, independent of hardfacts, so we don't only test what we can see.
   It skips digits that state nothing about the world (list enumerators, "passage 2",
   "summary in 88 words"), by the same fixed rule the RAGTruth bench uses.
3. Mutate it one of two ways:
   - fabricate: change its last digit so the new number appears nowhere in the prompt
     (the invented-tracking-number failure)
   - swap: replace the whole number it belongs to (2.1, not the 1 in 2.1) with a
     different whole number of the same shape that appears in the prompt as a whole
     number: a real source value in the wrong place, i.e. a Binding error. hardfacts is
     expected to miss most of these by design.

     (Until 2026-09-26 the swap drew raw digit fragments, so a quarter of "swaps" were
     really fabrications and the swap catch rate was overstated. The deep-check audit
     caught it; see docs/reviews/2026-09-26-deep-check.md.)
4. A mutation is caught when an Unsupported Claim overlaps the mutated characters.

Clean responses are also checked unmutated. The share that raise any flag is an
upper bound on the false-alarm rate, since annotators also miss real fabrications.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ragtruth import DETECTORS, HERE, commit  # noqa: E402

DIGITS = re.compile(r"\d+")
META = re.compile(
    r"(?m)^\s*\d{1,3}[.)]\s|\bpassages?\s+\d+|\b\d{1,4}[\s-]+(?:words?|sentences?|paragraphs?|bullet points?)\b", re.I
)
MONTHS = re.compile(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*$", re.I)


def shape(text: str, start: int, end: int) -> str:
    """A coarse, checker-independent label for what kind of value sits at text[start:end]."""
    before, after = text[max(0, start - 12):start], text[end:end + 8]
    if re.match(r"\s?%|\s?percent", after, re.I):
        return "percent"
    if re.search(r"[$€£¥]\s?[\d,.]*$|\b(?:RM|USD|MYR)\s?[\d,.]*$", before) or re.match(r"[\d,.]*\s?(?:dollars|ringgit)", after, re.I):
        return "money"
    if re.match(r":\d\d|\s?[ap]\.?m\b", after, re.I) or re.search(r"\d:$", before):
        return "time"
    if MONTHS.search(before) or re.match(r"(?:st|nd|rd|th)?,?\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)", after, re.I):
        return "date"
    if re.match(r"\d{3}\)|[-.\s]\d{3}[-.\s]\d{4}", after) or re.search(r"\(\d{3}\)\s?\d*$|\d{3}[-.]$", before):
        return "phone"
    if re.fullmatch(r"(1[89]|20)\d\d", text[start:end]):
        return "year"
    return "number"


def fabricate(token: str, prompt: str, rng: random.Random) -> str | None:
    for delta in rng.sample(range(1, 10), 9):
        new = token[:-1] + str((int(token[-1]) + delta) % 10)
        if new != token and not re.search(rf"(?<!\d){new}(?!\d)", prompt):
            return new
    return None


WHOLE = re.compile(r"(?<![\d.,])\d+(?:[.,]\d+)*(?!\d)")


def _shape(token: str) -> str:
    return re.sub(r"\d", "9", token)


def swap(output: str, m: re.Match, prompt: str, rng: random.Random) -> tuple[int, int, str] | None:
    """Replace the whole number around digit run `m` with another whole number from the prompt."""
    whole = next((w for w in WHOLE.finditer(output) if w.start() <= m.start() and m.end() <= w.end()), None)
    if whole is None:
        return None
    in_prompt = {w.group() for w in WHOLE.finditer(prompt)}
    if whole.group() not in in_prompt:
        return None
    value = whole.group().replace(",", "")
    pool = sorted(t for t in in_prompt if _shape(t) == _shape(whole.group()) and t.replace(",", "") != value)
    return (whole.start(), whole.end(), rng.choice(pool)) if pool else None


def run(split: str, data: Path, seed: int) -> dict:
    sources = {}
    with open(data / "source_info.jsonl", encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            sources[s["source_id"]] = s
    rng = random.Random(seed)
    caught: dict = defaultdict(Counter)       # (detector, mutation) -> Counter(shape -> caught)
    planted: dict = defaultdict(Counter)      # mutation -> Counter(shape -> planted)
    clean_flagged: Counter = Counter()
    clean_total: Counter = Counter()
    misses: list[str] = []
    with open(data / "response.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["split"] != split or r["labels"] or r.get("quality") not in (None, "good"):
                continue
            s = sources[r["source_id"]]
            prompt, output, task = s["prompt"], r["response"], s["task_type"]
            for name, detect in DETECTORS.items():
                clean_total[(name, task)] += 1
                clean_flagged[(name, task)] += bool(detect(output, prompt))
            meta = [x.span() for x in META.finditer(output)]
            eligible = [m for m in DIGITS.finditer(output)
                        if re.search(rf"(?<!\d){m.group()}(?!\d)", prompt)
                        and not any(a <= m.start() < b for a, b in meta)]
            if not eligible:
                continue
            m = rng.choice(eligible)
            kind = shape(output, m.start(), m.end())
            plants = {"fabricate": None, "swap": swap(output, m, prompt, rng)}
            new = fabricate(m.group(), prompt, rng)
            if new is not None:
                plants["fabricate"] = (m.start(), m.end(), new)
            for mutation, plant in plants.items():
                if plant is None:
                    continue
                a, b, new = plant
                mutated = output[:a] + new + output[b:]
                span = (a, a + len(new))
                planted[mutation][kind] += 1
                for name, detect in DETECTORS.items():
                    hit = any(a < span[1] and b > span[0] for a, b, _ in detect(mutated, prompt))
                    caught[(name, mutation)][kind] += hit
                    if name == "hardfacts" and mutation == "fabricate" and not hit and len(misses) < 400:
                        ctx = mutated[max(0, span[0] - 60):span[1] + 30].replace("\n", " ⏎ ")
                        misses.append(f"[{r['id']}] {kind} {m.group()}→{new} :: {ctx}")
    return {"planted": planted, "caught": caught, "clean_flagged": clean_flagged, "clean_total": clean_total,
            "misses": misses}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["train", "test"], default="train")
    ap.add_argument("--data", type=Path, default=HERE / "data")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--record", action="store_true")
    args = ap.parse_args()
    res = run(args.split, args.data, args.seed)
    rev = commit()
    out = {"split": args.split, "commit": rev, "recall": {}, "clean_flag_rate": {}}
    print(f"Fault injection · RAGTruth {args.split} clean responses · hardfacts @ {rev}\n")
    shapes = sorted(set().union(*[set(c) for c in res["planted"].values()]))
    for mutation in ("fabricate", "swap"):
        planted = res["planted"][mutation]
        print(f"{mutation:<10}" + "".join(f"{k:>10}" for k in shapes) + f"{'ALL':>10}")
        print(f"{'planted':<10}" + "".join(f"{planted[k]:>10}" for k in shapes) + f"{sum(planted.values()):>10}")
        for name in DETECTORS:
            c = res["caught"][(name, mutation)]
            rates = {k: c[k] / planted[k] if planted[k] else None for k in shapes}
            rates["ALL"] = sum(c.values()) / sum(planted.values())
            out["recall"].setdefault(mutation, {})[name] = {k: round(v, 4) if v is not None else None for k, v in rates.items()}
            print(f"{name:<10}" + "".join(f"{(rates[k] or 0):>10.3f}" for k in shapes) + f"{rates['ALL']:>10.3f}")
        print()
    print("clean responses with any flag (upper bound on false-alarm rate):")
    for name in DETECTORS:
        row = {}
        for task in ("QA", "Summary", "Data2txt"):
            t = res["clean_total"][(name, task)]
            row[task] = round(res["clean_flagged"][(name, task)] / t, 4) if t else None
        tot = sum(res["clean_total"][(name, t)] for t in ("QA", "Summary", "Data2txt"))
        row["ALL"] = round(sum(res["clean_flagged"][(name, t)] for t in ("QA", "Summary", "Data2txt")) / tot, 4)
        out["clean_flag_rate"][name] = row
        print(f"  {name:<10} " + "  ".join(f"{k}={v:.3f}" for k, v in row.items()) + f"  (n={tot})")
    (HERE / "out").mkdir(exist_ok=True)
    (HERE / "out" / f"fault-misses-{args.split}.txt").write_text("\n".join(res["misses"]) + "\n", encoding="utf-8")
    if args.record:
        (HERE / "results").mkdir(exist_ok=True)
        path = HERE / "results" / f"fault-{args.split}-{rev}.json"
        path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
        print(f"recorded → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
