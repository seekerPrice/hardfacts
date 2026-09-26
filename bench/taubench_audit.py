"""Blind audit of hardfacts' flags on tau-bench (no human labels exist there).

    uv run python bench/taubench.py                     # writes bench/out/taubench-flags.jsonl
    uv run python bench/taubench_audit.py sample --n 160 --batches 4 [--name taubench]
    # ...two independent auditors per batch write bench/audit/<name>/verdicts-NN.jsonl and
    #    bench/audit/<name>/second/verdicts-NN.jsonl, one JSON object per case...
    uv run python bench/taubench_audit.py summarize [--name taubench]

Audits: "taubench" audited the pre-registered run (bd9d22f); "taubench-postfix" the
checker after the fixes it led to, with Derivations (b0ab25d).

Each case is one flag: the Claim, the assistant turn it sits in, and a file holding
every Source the agent had seen by then (policy, user turns, tool results). Verdicts
use the RAGTruth audit's labels (bench/audit.py):
  invented       no Source states the value and it can't be computed from them (a correct flag)
  derived        computable from the Sources: a sum, difference, count (correct under ADR-0005)
  missed_support a Source states it, in a form hardfacts failed to read (a checker error)
  not_a_claim    the span asserts nothing checkable (a checker error)
plus, for derived values, "derived_correct": "yes" | "no" | "unclear" (is the arithmetic right?).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from audit import VERDICTS, agreement  # noqa: E402
from ragtruth import HERE, commit  # noqa: E402
from taubench import FILES, domain, tool_definitions, turns  # noqa: E402
from tau2bench import RUNS, label, trajectory  # noqa: E402

from hardfacts._check import _render  # noqa: E402

def _sources_text(name: str, run: int, turn: int, data: Path) -> str:
    if name in {label(r) for r in RUNS}:  # tau2-bench
        path = data.parent / "tau2" / f"{next(r for r in RUNS if label(r) == name)}.json"
        d = json.loads(path.read_text(encoding="utf-8"))
        env = d["info"]["environment_info"]
        traj = trajectory(d["simulations"][run], env["policy"])
        tools = (data.parent / "tau2" / "tools" / f"{env['domain_name']}.py").read_text(encoding="utf-8")
    else:
        traj = json.loads((data / f"{name}.json").read_text(encoding="utf-8"))[run]["traj"]
        tools = tool_definitions(data, domain(name))
    for i, _, sources in turns(traj, tools):
        if i == turn:
            return "\n\n".join(f"===== SOURCE {k} =====\n{_render(s)}" for k, s in enumerate(sources))
    raise KeyError(f"{name}/{run}/{turn}")


def sample(args) -> int:
    OUT = HERE / "audit" / args.name
    flags = [json.loads(line) for line in (HERE / "out" / f"{args.flags}-flags.jsonl").read_text(encoding="utf-8").splitlines()]
    pools = defaultdict(list)
    for f in flags:
        pools[f["id"].rsplit("/", 2)[0]].append(f)
    names = sorted(pools) if args.flags != "taubench" else list(FILES)
    rng = random.Random(args.seed)
    picked = [f for name in names for f in rng.sample(pools[name], min(args.n // len(names), len(pools[name])))]
    rng.shuffle(picked)
    (OUT / "cases").mkdir(parents=True, exist_ok=True)
    cases = []
    for f in picked:
        name, run, turn = f["id"].rsplit("/", 2)
        case = f"{f['id'].replace('/', '_')}_{f['span'][0]}"
        (OUT / "cases" / f"{case}.txt").write_text(_sources_text(name, int(run), int(turn), args.data), encoding="utf-8")
        a, b = f["span"]
        cases.append({"case": case, "agent": name, "kind": f["kind"], "claim": f["text"],
                      "context": f["output"][max(0, a - 300):b + 200], "turn": f["output"],
                      "sources_file": f"bench/audit/{args.name}/cases/{case}.txt"})
    size = -(-len(cases) // args.batches)
    for i in range(args.batches):
        with open(OUT / f"batch-{i + 1:02d}.jsonl", "w", encoding="utf-8") as fh:
            for c in cases[i * size:(i + 1) * size]:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    meta = {"commit": commit(), "flags": len(flags), "flags_by_agent": {k: len(v) for k, v in pools.items()},
            "sampled": len(cases), "seed": args.seed}
    (OUT / "sample.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0


def _verdicts(folder: Path) -> list[dict]:
    rows = []
    for path in sorted(folder.glob("verdicts-*.jsonl")):
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return rows


def summarize(args) -> int:
    OUT = HERE / "audit" / args.name
    meta = json.loads((OUT / "sample.json").read_text(encoding="utf-8"))
    first = _verdicts(OUT)
    bad = [v for v in first if v.get("verdict") not in VERDICTS]
    if bad:
        print(f"{len(bad)} verdicts with an unknown label, e.g. {bad[0]}", file=sys.stderr)
        return 2
    agent_of = {}
    for path in sorted(OUT.glob("batch-*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            agent_of[c["case"]] = c["agent"]
    counts = Counter(v["verdict"] for v in first)
    n = len(first)
    # Weight each agent's audited shares by its share of all flags, since the sample is stratified.
    strict = lenient = 0.0
    by_agent = {}
    for name, total in meta["flags_by_agent"].items():
        c = Counter(v["verdict"] for v in first if agent_of.get(v["case"]) == name)
        m = sum(c.values())
        by_agent[name] = dict(c)
        if m:
            strict += total * c["invented"] / m
            lenient += total * (c["invented"] + c["derived"]) / m
    derived = [v for v in first if v["verdict"] == "derived"]
    result = {
        "checker": meta["commit"], "flags": meta["flags"], "audited": n, "verdicts": dict(counts),
        "verdicts_by_agent": by_agent,
        "precision_invented": round(strict / meta["flags"], 4),
        "precision_invented_or_derived": round(lenient / meta["flags"], 4),
        "derived_arithmetic": dict(Counter(v.get("derived_correct", "unclear") for v in derived)),
    }
    second = {v["case"]: v["verdict"] for v in _verdicts(OUT / "second")} if (OUT / "second").is_dir() else {}
    if second:
        result["second_auditor"] = agreement([(v["verdict"], second[v["case"]]) for v in first if v["case"] in second])
    (OUT / "summary.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sample")
    s.add_argument("--n", type=int, default=160)
    s.add_argument("--batches", type=int, default=4)
    s.add_argument("--seed", type=int, default=0)
    s.add_argument("--data", type=Path, default=HERE / "data" / "taubench")
    s.add_argument("--flags", default="taubench", help="which run's flags: taubench or tau2bench")
    m = sub.add_parser("summarize")
    for p in (s, m):
        p.add_argument("--name", default="taubench", help="the audit's folder under bench/audit/")
    args = ap.parse_args()
    return sample(args) if args.cmd == "sample" else summarize(args)


if __name__ == "__main__":
    sys.exit(main())
