"""Out-of-sample check on FaithBench: scored once, with no rule tuned on it.

    bench/fetch_faithbench.sh
    uv run python bench/faithbench.py --record

FaithBench (Vectara, NAACL 2025) has 750 news summaries written by 10 modern LLMs.
Several human annotators marked the spans that aren't faithful to the source article.
Samples were chosen where existing detectors disagreed, so it is deliberately hard.

Its labels grade the spans: Unwanted (intrinsic or extrinsic), Questionable, and Benign
(information that isn't in the source but is true). hardfacts checks provenance, not
truth, so it is scored against two Gold definitions:
  unwanted       spans any annotator labelled Unwanted
  not-in-source  Unwanted, Questionable or Benign: anything the source doesn't back
The metrics and the naive baseline are the ones used for RAGTruth (bench/ragtruth.py).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ragtruth import DETECTORS, HERE, Tally, commit, context, flags_as_spans, is_hard_fact_span, overlaps  # noqa: E402

GOLD = {
    "unwanted": lambda labels: any(label.startswith("Unwanted") for label in labels),
    "not-in-source": lambda labels: True,
}


def load(data: Path) -> list[dict]:
    samples = []
    for path in sorted(data.glob("batch_*.json")):
        d = json.loads(path.read_text(encoding="utf-8"))
        samples += d["samples"] if isinstance(d, dict) else d
    return samples


def run(samples: list[dict], gold_name: str) -> dict[str, Tally]:
    is_gold = GOLD[gold_name]
    tallies = {name: Tally() for name in DETECTORS}
    for s in samples:
        spans = [(a["summary_start"], a["summary_end"], a["summary_span"]) for a in s["annotations"]
                 if a.get("summary_start") is not None and is_gold(a["label"] if isinstance(a["label"], list) else [a["label"]])]
        gold = [(a, b) for a, b, _ in spans]
        hard = [(a, b) for a, b, text in spans if is_hard_fact_span(text)]
        for name, detect in DETECTORS.items():
            t = tallies[name]
            t0 = time.perf_counter()
            flags = detect(s["summary"], s["source"])
            t.seconds += time.perf_counter() - t0
            t.responses += 1
            t.halluc_responses += bool(gold)
            t.flagged_responses += bool(flags)
            t.flagged_halluc_responses += bool(flags) and bool(gold)
            t.gold += len(gold)
            t.gold_caught += sum(overlaps(a, b, flags_as_spans(flags)) for a, b in gold)
            t.hard_gold += len(hard)
            t.hard_gold_caught += sum(overlaps(a, b, flags_as_spans(flags)) for a, b in hard)
            for a, b, label in flags:
                t.flags += 1
                if overlaps(a, b, gold):
                    t.flag_tp += 1
                else:
                    t.fp.append(context(s["sample_id"], s["summary"], a, b, label))
    return tallies


def fault_injection(samples: list[dict], seed: int = 0) -> dict:
    """The fault-injection protocol from bench/fault_injection.py, on FaithBench summaries."""
    import random
    import re
    from collections import Counter

    from fault_injection import DIGITS, META, fabricate, shape, swap

    rng = random.Random(seed)
    planted: dict = {"fabricate": Counter(), "swap": Counter()}
    caught: dict = {(d, m): Counter() for d in DETECTORS for m in planted}
    clean = {d: [0, 0] for d in DETECTORS}
    for s in samples:
        output, source = s["summary"], s["source"]
        for name, detect in DETECTORS.items():
            if not s["annotations"]:
                clean[name][0] += 1
                clean[name][1] += bool(detect(output, source))
        meta = [x.span() for x in META.finditer(output)]
        eligible = [m for m in DIGITS.finditer(output) if re.search(rf"(?<!\d){m.group()}(?!\d)", source)
                    and not any(a <= m.start() < b for a, b in meta)]
        if not eligible:
            continue
        m = rng.choice(eligible)
        kind = shape(output, m.start(), m.end())
        plants = {"fabricate": None, "swap": swap(output, m, source, rng)}
        new = fabricate(m.group(), source, rng)
        if new is not None:
            plants["fabricate"] = (m.start(), m.end(), new)
        for mutation, plant in plants.items():
            if plant is None:
                continue
            a0, b0, new = plant
            mutated = output[:a0] + new + output[b0:]
            span = (a0, a0 + len(new))
            planted[mutation][kind] += 1
            for name, detect in DETECTORS.items():
                caught[(name, mutation)][kind] += any(a < span[1] and b > span[0] for a, b, _ in detect(mutated, source))
    out = {}
    for mutation, p in planted.items():
        out[mutation] = {"planted": sum(p.values()), **{name: round(sum(caught[(name, mutation)].values()) / max(1, sum(p.values())), 4)
                                                     for name in DETECTORS}}
    out["clean_flag_rate"] = {name: {"responses": c[0], "rate": round(c[1] / c[0], 4) if c[0] else None} for name, c in clean.items()}
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=HERE / "data" / "faithbench")
    ap.add_argument("--record", action="store_true")
    args = ap.parse_args()
    samples = load(args.data)
    if not samples:
        print("FaithBench not found; run bench/fetch_faithbench.sh", file=sys.stderr)
        return 2
    rev = commit()
    print(f"FaithBench · {len(samples)} summaries · hardfacts @ {rev}\n")
    header = f"{'gold':<14} {'detector':<10} {'span P':>7} {'hard R':>7} {'all R':>6} {'resp P':>7} {'flags':>6} {'hard gold':>9}"
    print(header)
    print("-" * len(header))
    results = {"dataset": "FaithBench", "commit": rev, "samples": len(samples), "gold": {}}
    for gold_name in GOLD:
        results["gold"][gold_name] = {}
        tallies = run(samples, gold_name)
        for name, t in tallies.items():
            m = t.metrics()
            results["gold"][gold_name][name] = m
            fmt = lambda v: f"{v:.3f}" if isinstance(v, float) else str(v)  # noqa: E731
            print(f"{gold_name:<14} {name:<10} {fmt(m['span_precision']):>7} {fmt(m['hard_fact_recall']):>7} "
                  f"{fmt(m['all_span_recall']):>6} {fmt(m['response_precision']):>7} {m['flags']:>6} {m['hard_gold']:>9}")
        if gold_name == "not-in-source":
            out = HERE / "out"
            out.mkdir(exist_ok=True)
            (out / "faithbench-unmatched.txt").write_text("\n".join(tallies["hardfacts"].fp) + "\n", encoding="utf-8")
    fi = fault_injection(samples)
    results["fault_injection"] = fi
    print(f"\nfault injection: {json.dumps(fi)}")
    if args.record:
        path = HERE / "results" / f"faithbench-{rev}.json"
        path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"\nrecorded → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
