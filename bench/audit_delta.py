"""Audit only what a new checker changed: the flags it adds, relative to an audited release.

    uv run python bench/audit_delta.py sample --base 78413c9 --split test
    # ...auditors write bench/audit/test-delta-<head>/verdicts-NN.jsonl (and second/…), labels as bench/audit.py...
    uv run python bench/audit_delta.py summarize --base 78413c9 --split test

Every unmatched test flag of the base release has two blind verdicts (bench/audit/test/). A new
release keeps the verdicts of flags it still raises, drops those of flags it no longer raises, and
needs verdicts only for the flags it adds. So audits compound across releases instead of starting over.
The base checker is loaded from `git archive <base> src`, never from the working tree.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audit import VERDICTS, agreement  # noqa: E402
from ragtruth import HERE, commit, overlaps  # noqa: E402

FLAGS = """
import json, sys
from hardfacts import check
data, split = sys.argv[1], sys.argv[2]
src = {}
for line in open(data + "/source_info.jsonl", encoding="utf-8"):
    s = json.loads(line); src[s["source_id"]] = s
for line in open(data + "/response.jsonl", encoding="utf-8"):
    r = json.loads(line)
    if r["split"] != split:
        continue
    for c in check(r["response"], [src[r["source_id"]]["prompt"]]).unsupported:
        print(json.dumps({"id": r["id"], "span": list(c.span), "kind": c.kind, "text": c.text}))
"""


def flags(src: Path | None, data: Path, split: str) -> list[dict]:
    """Every Unsupported Claim on the split, from the checker at ``src`` (None: the working tree)."""
    env_path = [] if src is None else ["env", f"PYTHONPATH={src}"]
    out = subprocess.run([*env_path, "uv", "run", "python", "-c", FLAGS, str(data), split],
                         capture_output=True, text=True, check=True, cwd=HERE.parent).stdout
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def base_flags(base: str, data: Path, split: str) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        archive = subprocess.run(["git", "archive", base, "src"], capture_output=True, check=True, cwd=HERE.parent).stdout
        subprocess.run(["tar", "-x", "-C", tmp], input=archive, check=True)
        return flags(Path(tmp) / "src", data, split)


def key(f: dict) -> tuple:
    return f["id"], tuple(f["span"])


def unmatched(rows: list[dict], data: Path, split: str) -> list[dict]:
    """Flags that overlap no Gold span: the ones an audit decides."""
    gold = {}
    for line in (data / "response.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["split"] == split:
            gold[r["id"]] = ([(lab["start"], lab["end"]) for lab in r["labels"]], r["response"])
    return [f | {"response": gold[f["id"]][1]} for f in rows if not overlaps(*f["span"], gold[f["id"]][0])]


def sample(args) -> int:
    head = commit()
    out = HERE / "audit" / f"{args.split}-delta-{head}"
    old = {key(f) for f in base_flags(args.base, args.data, args.split)}
    new = unmatched(flags(None, args.data, args.split), args.data, args.split)
    added = [f for f in new if key(f) not in old]
    sources = {}
    for line in (args.data / "source_info.jsonl").read_text(encoding="utf-8").splitlines():
        s = json.loads(line)
        sources[s["source_id"]] = s
    responses = {json.loads(line)["id"]: json.loads(line) for line in (args.data / "response.jsonl").read_text(encoding="utf-8").splitlines()}
    out.mkdir(parents=True, exist_ok=True)
    cases = []
    for f in added:
        r = responses[f["id"]]
        a, b = f["span"]
        cases.append({"case": f"{f['id']}:{a}", "task": sources[r["source_id"]]["task_type"], "kind": f["kind"], "claim": f["text"],
                      "context": r["response"][max(0, a - 250):b + 150], "response": r["response"],
                      "source": sources[r["source_id"]]["prompt"]})
    with open(out / "batch-01.jsonl", "w", encoding="utf-8") as fh:
        for c in cases:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    meta = {"base": args.base, "head": head, "split": args.split, "added_unmatched": len(added)}
    (out / "sample.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0


def summarize(args) -> int:
    """Audited precision of the new release: carried-over base verdicts plus the delta's verdicts."""
    head = commit()
    out = HERE / "audit" / f"{args.split}-delta-{head}"
    base_verdicts = {}
    for path in sorted((HERE / "audit" / args.split).glob("verdicts-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                v = json.loads(line)
                base_verdicts[v["case"]] = v["verdict"]
    delta = [json.loads(line) for path in sorted(out.glob("verdicts-*.jsonl")) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(v.get("verdict") not in VERDICTS for v in delta):
        print("unknown verdict label in the delta audit", file=sys.stderr)
        return 2
    rows = flags(None, args.data, args.split)
    still = unmatched(rows, args.data, args.split)
    verdicts = Counter()
    missing = 0
    delta_by_case = {v["case"]: v["verdict"] for v in delta}
    for f in still:
        case = f"{f['id']}:{f['span'][0]}"
        verdict = delta_by_case.get(case) or base_verdicts.get(case)
        if verdict is None:
            missing += 1
        else:
            verdicts[verdict] += 1
    tp = len(rows) - len(still)
    result = {
        "base": args.base, "head": head, "flags": len(rows), "flags_on_gold": tp, "unmatched": len(still),
        "unmatched_without_a_verdict": missing, "verdicts": dict(verdicts),
        "gold_precision": round(tp / len(rows), 4),
        "audited_precision_strict": round((tp + verdicts["invented"]) / len(rows), 4),
        "audited_precision_with_derived": round((tp + verdicts["invented"] + verdicts["derived"]) / len(rows), 4),
    }
    second = {json.loads(line)["case"]: json.loads(line)["verdict"] for path in sorted((out / "second").glob("verdicts-*.jsonl"))
              for line in path.read_text(encoding="utf-8").splitlines() if line.strip()} if (out / "second").is_dir() else {}
    if second:
        result["second_auditor_on_delta"] = agreement([(v["verdict"], second[v["case"]]) for v in delta if v["case"] in second])
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("sample", "summarize"):
        p = sub.add_parser(name)
        p.add_argument("--base", required=True, help="the audited release commit, e.g. 78413c9")
        p.add_argument("--split", choices=["train", "test"], default="test")
        p.add_argument("--data", type=Path, default=HERE / "data")
    args = ap.parse_args()
    return sample(args) if args.cmd == "sample" else summarize(args)


if __name__ == "__main__":
    sys.exit(main())
