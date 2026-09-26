"""Audit the flags that don't overlap a Gold span: are they wrong, or did the annotators miss them?

    uv run python bench/audit.py sample --split train --n 120 --batches 4
    # ...auditors write bench/audit/<split>/verdicts-NN.jsonl, one JSON object per case...
    uv run python bench/audit.py summarize --split train

Every flag that misses a Gold span counts as a false positive in ragtruth.py. Some are
real: RAGTruth annotators miss fabrications, and one Source's six responses are
sometimes labelled inconsistently. This script samples those flags, stratified by
task, for a line-by-line audit, then turns the verdicts into an audited precision.

Verdicts (field "verdict"):
  invented       the Source does not state the value and it can't be computed from it (a correct flag)
  derived        not stated, but computable from the Source: conversion, sum, count (correct under ADR-0005)
  missed_support the Source does state it, in a form hardfacts failed to read (a checker error)
  not_a_claim    the span asserts nothing checkable: a name, idiom, formatting (a checker error)
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ragtruth import HERE, commit, overlaps  # noqa: E402

from hardfacts import check  # noqa: E402

VERDICTS = ("invented", "derived", "missed_support", "not_a_claim")


def load(data: Path, split: str):
    sources = {}
    with open(data / "source_info.jsonl", encoding="utf-8") as f:
        for line in f:
            s = json.loads(line)
            sources[s["source_id"]] = s
    with open(data / "response.jsonl", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r["split"] == split:
                yield r, sources[r["source_id"]]


def sample(args) -> int:
    pools: dict[str, list] = {"QA": [], "Summary": [], "Data2txt": []}
    flags = tp = 0
    for r, s in load(args.data, args.split):
        gold = [(lab["start"], lab["end"]) for lab in r["labels"]]
        for c in check(r["response"], [s["prompt"]]).unsupported:
            flags += 1
            if overlaps(*c.span, gold):
                tp += 1
                continue
            a, b = c.span
            pools[s["task_type"]].append({
                "case": f"{r['id']}:{a}", "task": s["task_type"], "kind": c.kind, "claim": c.text,
                "context": r["response"][max(0, a - 250):b + 150], "response": r["response"], "source": s["prompt"],
            })
    rng = random.Random(args.seed)
    per_task = args.n // 3
    picked = [case for pool in pools.values() for case in rng.sample(pool, min(per_task, len(pool)))]
    rng.shuffle(picked)
    out = HERE / "audit" / args.split
    out.mkdir(parents=True, exist_ok=True)
    size = -(-len(picked) // args.batches)
    for i in range(args.batches):
        with open(out / f"batch-{i + 1:02d}.jsonl", "w", encoding="utf-8") as f:
            for case in picked[i * size:(i + 1) * size]:
                f.write(json.dumps(case, ensure_ascii=False) + "\n")
    meta = {"split": args.split, "commit": commit(), "flags": flags, "flags_on_gold": tp,
            "unmatched_by_task": {k: len(v) for k, v in pools.items()}, "sampled": len(picked), "seed": args.seed}
    (out / "sample.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0


def kappa(pairs: list[tuple[str, str]]) -> float:
    """Cohen's kappa for two raters over the same cases."""
    n = len(pairs)
    observed = sum(a == b for a, b in pairs) / n
    labels = {x for pair in pairs for x in pair}
    expected = sum((sum(a == k for a, _ in pairs) / n) * (sum(b == k for _, b in pairs) / n) for k in labels)
    return (observed - expected) / (1 - expected) if expected < 1 else 1.0


def agreement(pairs: list[tuple[str, str]]) -> dict:
    """Agreement between two independent auditors, on all four labels and on correct-vs-error."""
    correct = {"invented", "derived"}
    binary = [(a in correct, b in correct) for a, b in pairs]
    return {
        "cases": len(pairs),
        "four_way_agreement": round(sum(a == b for a, b in pairs) / len(pairs), 4),
        "four_way_kappa": round(kappa(pairs), 4),
        "flag_correct_agreement": round(sum(a == b for a, b in binary) / len(binary), 4),
        "flag_correct_kappa": round(kappa([(str(a), str(b)) for a, b in binary]), 4),
        "disagreements": [f"{a} vs {b}" for a, b in pairs if a != b],
    }


def summarize(args) -> int:
    out = HERE / "audit" / args.split
    meta = json.loads((out / "sample.json").read_text(encoding="utf-8"))
    verdicts = []
    for path in sorted(out.glob("verdicts-*.jsonl")):
        verdicts += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    bad = [v for v in verdicts if v.get("verdict") not in VERDICTS]
    if bad:
        print(f"{len(bad)} verdicts with an unknown label, e.g. {bad[0]}", file=sys.stderr)
        return 2
    counts = Counter(v["verdict"] for v in verdicts)
    by_task = {t: Counter(v["verdict"] for v in verdicts if v.get("task") == t) for t in ("QA", "Summary", "Data2txt")}
    n = len(verdicts)
    flags, gold_tp = meta["flags"], meta["flags_on_gold"]
    unmatched = flags - gold_tp
    # Extrapolate by task: each task's unmatched flags carry that task's audited share.
    correct_strict = correct_lenient = 0.0
    for task, c in by_task.items():
        m = sum(c.values())
        if m:
            correct_strict += meta["unmatched_by_task"][task] * c["invented"] / m
            correct_lenient += meta["unmatched_by_task"][task] * (c["invented"] + c["derived"]) / m
    result = {
        "split": meta["split"], "audited": n, "verdicts": dict(counts),
        "verdicts_by_task": {t: dict(c) for t, c in by_task.items()},
        "gold_precision": round(gold_tp / flags, 4),
        "audited_precision_strict": round((gold_tp + correct_strict) / flags, 4),
        "audited_precision_with_derived": round((gold_tp + correct_lenient) / flags, 4),
        "unmatched_flags": unmatched,
    }
    second = {}
    for path in sorted((out / "second").glob("verdicts-*.jsonl")) if (out / "second").is_dir() else []:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                v = json.loads(line)
                second[v["case"]] = v["verdict"]
    if second:
        pairs = [(v["verdict"], second[v["case"]]) for v in verdicts if v["case"] in second]
        result["second_auditor"] = agreement(pairs)
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sample", "summarize"):
        p = sub.add_parser(name)
        p.add_argument("--split", choices=["train", "test"], default="train")
        p.add_argument("--data", type=Path, default=HERE / "data")
    sub.choices["sample"].add_argument("--n", type=int, default=120)
    sub.choices["sample"].add_argument("--batches", type=int, default=4)
    sub.choices["sample"].add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    return sample(args) if args.cmd == "sample" else summarize(args)


if __name__ == "__main__":
    sys.exit(main())
