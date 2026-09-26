"""Blind audit of hardfacts' flags on RAGBench responses the GPT-4 annotator judged adherent.

    uv run --with pyarrow python bench/ragbench_audit.py sample --n 60 --batches 2
    # ...two independent auditors per batch write bench/audit/ragbench/verdicts-NN.jsonl and
    #    bench/audit/ragbench/second/verdicts-NN.jsonl...
    uv run python bench/ragbench_audit.py summarize

hardfacts flags an unexplained value in 4.6% of the adherent responses in the ten non-numeric
subsets. Either the annotator passed a wrong number or hardfacts is wrong. Auditors see the value,
the response and the documents, but not the annotator's verdict. Labels are bench/audit.py's:
invented, derived, missed_support, not_a_claim. One flag is sampled per response, seeded.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audit import VERDICTS, agreement  # noqa: E402
from ragbench import HERE, NUMERIC, rows  # noqa: E402

from hardfacts import check  # noqa: E402

OUT = HERE / "audit" / "ragbench"


def sample(args) -> int:
    rng = random.Random(args.seed)
    pool = []
    for r in rows(HERE / "data" / "ragbench"):
        if r["subset"] in NUMERIC or not r["adherence_score"]:
            continue
        sources = [d for d in r["documents"] if d]
        unexplained = check(r["response"] or "", sources).unexplained
        if unexplained:
            c = rng.choice(unexplained)
            pool.append((r, sources, c))
    picked = rng.sample(pool, min(args.n, len(pool)))
    (OUT / "cases").mkdir(parents=True, exist_ok=True)
    cases = []
    for r, sources, c in picked:
        case = f"{r['subset']}_{r['id']}"
        (OUT / "cases" / f"{case}.txt").write_text(
            "\n\n".join(f"===== DOCUMENT {k} =====\n{d}" for k, d in enumerate(sources)), encoding="utf-8")
        cases.append({"case": case, "subset": r["subset"], "kind": c.kind, "claim": c.text,
                      "response": r["response"], "sources_file": f"bench/audit/ragbench/cases/{case}.txt"})
    size = -(-len(cases) // args.batches)
    for i in range(args.batches):
        with open(OUT / f"batch-{i + 1:02d}.jsonl", "w", encoding="utf-8") as f:
            for c in cases[i * size:(i + 1) * size]:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
    (OUT / "sample.json").write_text(json.dumps({"pool": len(pool), "sampled": len(cases), "seed": args.seed}) + "\n")
    print(f"{len(pool)} adherent responses with a flag; sampled {len(cases)} into {args.batches} batches")
    return 0


def _verdicts(folder: Path) -> list[dict]:
    return [json.loads(line) for p in sorted(folder.glob("verdicts-*.jsonl"))
            for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]


def summarize(_args) -> int:
    first, second = _verdicts(OUT), {v["case"]: v["verdict"] for v in _verdicts(OUT / "second")}
    bad = [v for v in first if v.get("verdict") not in VERDICTS]
    if bad:
        print(f"unknown verdicts: {bad[:2]}", file=sys.stderr)
        return 2
    counts = Counter(v["verdict"] for v in first)
    n = len(first)
    result = {"audited": n, "verdicts": dict(counts),
              "correct_flags": round((counts["invented"] + counts["derived"]) / n, 4),
              "invented": round(counts["invented"] / n, 4),
              "checker_errors": round((counts["missed_support"] + counts["not_a_claim"]) / n, 4)}
    if second:
        result["second_auditor"] = agreement([(v["verdict"], second[v["case"]]) for v in first if v["case"] in second])
    (OUT / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--n", type=int, default=60)
    s.add_argument("--batches", type=int, default=2)
    s.add_argument("--seed", type=int, default=0)
    sub.add_parser("summarize")
    args = ap.parse_args()
    return sample(args) if args.cmd == "sample" else summarize(args)


if __name__ == "__main__":
    sys.exit(main())
