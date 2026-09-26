"""Benchmark hardfacts against RAGTruth's human hallucination spans.

Usage:
    uv run python bench/ragtruth.py --split train          # development (ADR-0004)
    uv run python bench/ragtruth.py --split test --record  # release numbers only

The Source for each response is the full prompt the model was given, since that is
everything it saw. A Flag is an Unsupported Claim; it is a true positive when it
overlaps a Gold span.

"Hard-fact hallucinations" are Gold spans that still contain a digit after removing
line-leading list enumerators ("5. ") and "passage N" citations. The definition is a
fixed regex that lives here, not in the checker, so recall stays comparable across
versions and between detectors.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from hardfacts import check

HERE = Path(__file__).parent
DIGIT = re.compile(r"\d")
NOT_A_FACT = re.compile(r"(?m)^\s*\d{1,3}[.)]\s|\bpassages?\s+\d+(?:\s*(?:,|and|&)\s*\d+)*", re.I)


def is_hard_fact_span(text: str) -> bool:
    return bool(DIGIT.search(NOT_A_FACT.sub(" ", text)))


NAIVE_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def naive_flags(output: str, source: str) -> list[tuple[int, int, str]]:
    """The baseline: every digit string in the Output must appear in the Source."""
    norm = lambda s: s.replace(",", "")  # noqa: E731
    known = {norm(m.group()) for m in NAIVE_NUMBER.finditer(source)}
    return [(m.start(), m.end(), m.group()) for m in NAIVE_NUMBER.finditer(output) if norm(m.group()) not in known]


def hardfacts_flags(output: str, source: str) -> list[tuple[int, int, str]]:
    report = check(output, [source])
    return [(c.span[0], c.span[1], f"{c.kind}:{c.text}") for c in report.unsupported]


DETECTORS = {"naive": naive_flags, "hardfacts": hardfacts_flags}


@dataclass
class Tally:
    flags: int = 0
    flag_tp: int = 0
    gold: int = 0
    gold_caught: int = 0
    hard_gold: int = 0
    hard_gold_caught: int = 0
    responses: int = 0
    halluc_responses: int = 0
    flagged_responses: int = 0
    flagged_halluc_responses: int = 0
    seconds: float = 0.0
    fp: list = field(default_factory=list)
    fn: list = field(default_factory=list)

    def metrics(self) -> dict:
        div = lambda a, b: round(a / b, 4) if b else None  # noqa: E731
        return {
            "span_precision": div(self.flag_tp, self.flags),
            "hard_fact_recall": div(self.hard_gold_caught, self.hard_gold),
            "all_span_recall": div(self.gold_caught, self.gold),
            "response_precision": div(self.flagged_halluc_responses, self.flagged_responses),
            "response_recall": div(self.flagged_halluc_responses, self.halluc_responses),
            "flags": self.flags,
            "flags_true": self.flag_tp,
            "hard_gold": self.hard_gold,
            "responses": self.responses,
            "flagged_responses": self.flagged_responses,
            "us_per_response": round(self.seconds / self.responses * 1e6, 1) if self.responses else None,
        }


def overlaps(a: int, b: int, spans) -> bool:
    return any(a < end and b > start for start, end in spans)


def run(split: str, data: Path, task_filter: str | None, seed: int) -> dict[str, dict[str, Tally]]:
    sources = {}
    with open(data / "source_info.jsonl", encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            sources[s["source_id"]] = s
    tallies: dict[str, dict[str, Tally]] = {d: defaultdict(Tally) for d in DETECTORS}
    with open(data / "response.jsonl", encoding="utf-8") as f:
        responses = [json.loads(line) for line in f]
    for r in responses:
        if r["split"] != split:
            continue
        s = sources[r["source_id"]]
        task = s["task_type"]
        if task_filter and task != task_filter:
            continue
        prompt, output = s["prompt"], r["response"]
        gold = [(lab["start"], lab["end"]) for lab in r["labels"]]
        hard = [(lab["start"], lab["end"]) for lab in r["labels"] if is_hard_fact_span(lab["text"])]
        for name, detect in DETECTORS.items():
            t0 = time.perf_counter()
            flags = detect(output, prompt)
            elapsed = time.perf_counter() - t0
            for t in (tallies[name][task], tallies[name]["ALL"]):
                t.seconds += elapsed
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
                    elif t is tallies[name][task]:
                        t.fp.append(context(r["id"], output, a, b, label))
            if name == "hardfacts":
                for a, b in hard:
                    if not overlaps(a, b, flags_as_spans(flags)):
                        tallies[name][task].fn.append(context(r["id"], output, a, b, "missed"))
    random.seed(seed)
    return tallies


def flags_as_spans(flags):
    return [(a, b) for a, b, _ in flags]


def context(rid, text: str, a: int, b: int, label: str) -> str:
    left = text[max(0, a - 60):a].replace("\n", " ⏎ ")
    right = text[b:b + 40].replace("\n", " ⏎ ")
    return f"[{rid}] {label} :: …{left}⟦{text[a:b]}⟧{right}…"


def commit() -> str:
    """The checker's commit for recorded results; HARDFACTS_CHECKER_COMMIT names a pinned
    checker loaded through PYTHONPATH (re-measuring a release with a fixed harness)."""
    pinned = os.environ.get("HARDFACTS_CHECKER_COMMIT")
    if pinned:
        return f"{pinned}-pinned"
    try:
        root = HERE.parent
        sha = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], cwd=root, text=True).strip()
        dirty = subprocess.call(["git", "diff", "--quiet", "HEAD", "--", "src", "ts/src"], cwd=root) != 0
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", choices=["train", "test"], default="train")
    ap.add_argument("--data", type=Path, default=HERE / "data")
    ap.add_argument("--task", choices=["QA", "Summary", "Data2txt"])
    ap.add_argument("--samples", type=int, default=25, help="FP/FN examples to dump per task")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--record", action="store_true", help="write results to bench/results/")
    args = ap.parse_args()
    if not (args.data / "response.jsonl").exists():
        print(f"RAGTruth not found in {args.data}; run bench/fetch_ragtruth.sh", file=sys.stderr)
        return 2

    tallies = run(args.split, args.data, args.task, args.seed)
    rev = commit()
    print(f"RAGTruth {args.split} · hardfacts @ {rev}\n")
    header = f"{'detector':<10} {'task':<9} {'span P':>7} {'hard R':>7} {'all R':>6} {'resp P':>7} {'resp R':>7} {'flags':>6} {'µs/resp':>8}"
    print(header)
    print("-" * len(header))
    results = {"split": args.split, "commit": rev, "detectors": {}}
    for name, by_task in tallies.items():
        results["detectors"][name] = {}
        for task in ["QA", "Summary", "Data2txt", "ALL"]:
            if task not in by_task:
                continue
            m = by_task[task].metrics()
            results["detectors"][name][task] = m
            fmt = lambda v: f"{v:.3f}" if isinstance(v, float) else str(v)  # noqa: E731
            print(f"{name:<10} {task:<9} {fmt(m['span_precision']):>7} {fmt(m['hard_fact_recall']):>7} "
                  f"{fmt(m['all_span_recall']):>6} {fmt(m['response_precision']):>7} {fmt(m['response_recall']):>7} "
                  f"{m['flags']:>6} {m['us_per_response']:>8}")
        print()

    out = HERE / "out"
    out.mkdir(exist_ok=True)
    rng = random.Random(args.seed)
    with open(out / f"errors-{args.split}.txt", "w", encoding="utf-8") as f:
        for task, t in tallies["hardfacts"].items():
            if task == "ALL":
                continue
            for kind, items in (("FALSE POSITIVES", t.fp), ("MISSED HARD-FACT SPANS", t.fn)):
                f.write(f"===== {task} · {kind} ({len(items)}) =====\n")
                for line in rng.sample(items, min(args.samples, len(items))):
                    f.write(line + "\n")
                f.write("\n")
    print(f"error samples → {out / f'errors-{args.split}.txt'}")

    if args.record:
        rec = HERE / "results"
        rec.mkdir(exist_ok=True)
        path = rec / f"{args.split}-{rev}.json"
        path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"recorded → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
