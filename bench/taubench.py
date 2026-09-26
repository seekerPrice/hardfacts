"""hardfacts on tau-bench: real customer-service agents answering from JSON tool results.

    bench/fetch_taubench.sh
    uv run python bench/taubench.py --record

RAGTruth is news, QA and Yelp text. The use case hardfacts is built for (a support
bot stating order IDs, prices, dates and phone numbers from tool results) has no
labelled benchmark, so this run uses tau-bench's published trajectories (Sierra, MIT):
GPT-4o and Claude 3.5 Sonnet (new) as retail and airline agents, with every tool
result they saw.

Every assistant turn with text is an Output. Its Sources are what the agent had seen
by then: the policy (system prompt), the tool definitions it was given, the user's
turns, and the tool results, passed as parsed JSON the way an integration would pass
them. Earlier assistant turns are not Sources: they are outputs too.

There are no hallucination labels, so the run reports:
- flags per turn for hardfacts and for the naive check (every digit string must appear
  in the Sources), and how often each flags turns of failed vs successful tasks;
- fault injection, as on RAGTruth: one digit of a value the Sources contain is changed
  so the new value appears nowhere in them, and a catch is a flag over the change;
- every hardfacts flag, written to bench/out/taubench-flags.jsonl for a blind audit
  (bench/audit/taubench/).

Protocol: scored once, as-is, before any flag is read (docs/adr/0004 applied to a
dataset never used for tuning). Fixes found by the audit are reported separately.

(The first recorded run, taubench-bd9d22f.json, planted fabrications in list markers
("1." → "3."), which state nothing and which the RAGTruth harness always skipped: 2,260
of its 3,413 misses. The harness was corrected and the same checker re-measured,
pinned: taubench-bd9d22f-pinned.json. Both runs also left out the tool definitions,
which are part of every prompt but not of the trajectory files, so an agent quoting a
schema's example ("a code like 'ZFA04Y'") was flagged. From taubench-*-tools.json on,
the definitions are a Source.)
"""

from __future__ import annotations

import argparse
import ast
import json
import random
import re
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fault_injection import META, fabricate  # noqa: E402
from ragtruth import HERE, commit, naive_flags  # noqa: E402

from hardfacts import check  # noqa: E402
from hardfacts._check import _render  # noqa: E402

FILES = ("gpt-4o-retail", "gpt-4o-airline", "sonnet-35-new-retail", "sonnet-35-new-airline")
DIGITS = re.compile(r"\d+")


def tool_definitions(data: Path, domain: str) -> list[dict]:
    """Each tool's get_info() schema, read from its source file without importing tau-bench."""
    schemas = []
    for path in sorted((data / "tools" / domain).glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name == "get_info":
                ret = next(n for n in ast.walk(node) if isinstance(n, ast.Return))
                schemas.append(ast.literal_eval(ret.value))
    if not schemas:
        raise FileNotFoundError(f"no tool definitions under {data / 'tools' / domain}: run bench/fetch_taubench.sh")
    return schemas


def _source(message: dict):
    content = message.get("content") or ""
    if message["role"] == "tool":
        try:
            return json.loads(content)
        except ValueError:
            return content
    return content


def turns(trajectory: list[dict], tools: list[dict]):
    """(turn index, assistant text, Sources seen so far) for every assistant turn with text."""
    seen: list = [{"tools": tools}]
    for i, m in enumerate(trajectory):
        if m["role"] == "assistant":
            if isinstance(m.get("content"), str) and m["content"].strip():
                yield i, m["content"], list(seen)
        elif m.get("content"):
            seen.append(_source(m))


def domain(name: str) -> str:
    return "airline" if name.endswith("airline") else "retail"


def score(job: tuple[str, int, dict, list]) -> dict:
    name, n, run, tools = job
    rng = random.Random(f"{name}:{n}")
    out = {"turns": 0, "turns_with_claims": 0, "claims": Counter(), "flags": Counter(), "turns_flagged": 0,
           "naive_flags": 0, "naive_turns_flagged": 0, "planted": 0, "caught": 0, "naive_caught": 0, "records": [],
           "flags_with_derivation": 0, "caught_with_derivation": 0}
    for i, text, sources in turns(run["traj"], tools):
        report = check(text, sources)
        joined = "\n".join(_render(s) for s in sources)
        naive = naive_flags(text, joined)
        out["turns"] += 1
        out["turns_with_claims"] += bool(report.claims)
        out["claims"].update(c.kind for c in report.claims)
        out["flags"].update(c.kind for c in report.unsupported)
        out["turns_flagged"] += not report.ok
        out["naive_flags"] += len(naive)
        out["naive_turns_flagged"] += bool(naive)
        out["flags_with_derivation"] += sum(c.derivation is not None for c in report.unsupported)
        for c in report.unsupported:
            out["records"].append({"id": f"{name}/{n}/{i}", "kind": c.kind, "text": c.text, "span": list(c.span),
                                   "output": text, "reward": run["reward"],
                                   "derivation": c.derivation.expression if c.derivation else None})
        meta = [x.span() for x in META.finditer(text)]  # list markers state nothing, as in the RAGTruth harness
        eligible = [m for m in DIGITS.finditer(text) if re.search(rf"(?<!\d){m.group()}(?!\d)", joined)
                    and not any(a <= m.start() < b for a, b in meta)]
        if eligible:
            m = rng.choice(eligible)
            new = fabricate(m.group(), joined, rng)
            if new is not None:
                mutated = text[:m.start()] + new + text[m.end():]
                a, b = m.start(), m.start() + len(new)
                out["planted"] += 1
                hits = [c for c in check(mutated, sources).unsupported if c.span[0] < b and c.span[1] > a]
                out["caught"] += bool(hits)
                out["caught_with_derivation"] += any(c.derivation is not None for c in hits)  # a coincidence (ADR-0007)
                out["naive_caught"] += any(x < b and y > a for x, y, _ in naive_flags(mutated, joined))
    out["reward"] = run["reward"]
    return out


def evaluate(jobs: list, names: list[str], dataset: str, stem: str, record: bool, label: str = "") -> dict:
    """Score every job, print the table, write every flag to bench/out/<stem>-flags.jsonl, and
    (with ``record``) the summary to bench/results/<stem>-<commit>[-label].json. Shared with tau2bench.py."""
    rev = commit()
    with Pool() as pool:
        scored = pool.map(score, jobs, chunksize=8)
    result: dict = {"dataset": dataset, "commit": rev, "by_agent": {}}
    records = []
    print(f"hardfacts on {dataset} · checker @ {rev}\n")
    width = max(24, max(len(n) for n in names) + 2)
    print(f"{'agent':<{width}}{'runs':>6}{'turns':>7}{'claims':>8}{'flags':>7}{'turns flagged':>15}{'naive':>7}{'naive turns':>13}"
          f"{'fab caught':>12}{'naive':>7}")
    for name in (*names, "ALL"):
        rows = [(job, s) for job, s in zip(jobs, scored) if name in ("ALL", job[0])]
        agg = {k: sum(s[k] for _, s in rows) for k in ("turns", "turns_with_claims", "turns_flagged", "naive_flags",
                                                        "naive_turns_flagged", "planted", "caught", "naive_caught",
                                                        "flags_with_derivation", "caught_with_derivation")}
        claims = sum((s["claims"] for _, s in rows), Counter())
        flags = sum((s["flags"] for _, s in rows), Counter())
        by_reward = {}
        for outcome, want in (("success", 1.0), ("failure", 0.0)):
            part = [s for _, s in rows if s["reward"] == want]
            t = sum(s["turns"] for s in part)
            by_reward[outcome] = {"runs": len(part), "turns": t,
                                  "turns_flagged": round(sum(s["turns_flagged"] for s in part) / t, 4) if t else None,
                                  "naive_turns_flagged": round(sum(s["naive_turns_flagged"] for s in part) / t, 4) if t else None}
        entry = {
            "runs": len(rows), **agg,
            "claims": dict(claims.most_common()), "flags": dict(flags.most_common()),
            "share_turns_flagged": round(agg["turns_flagged"] / max(1, agg["turns"]), 4),
            "naive_share_turns_flagged": round(agg["naive_turns_flagged"] / max(1, agg["turns"]), 4),
            "fabrications_caught": round(agg["caught"] / agg["planted"], 4) if agg["planted"] else None,
            "naive_fabrications_caught": round(agg["naive_caught"] / agg["planted"], 4) if agg["planted"] else None,
            "by_reward": by_reward,
            "share_flags_with_derivation": round(agg["flags_with_derivation"] / max(1, sum(flags.values())), 4),
            "share_caught_fabrications_with_derivation": round(agg["caught_with_derivation"] / max(1, agg["caught"]), 4),
        }
        result["by_agent"][name] = entry
        print(f"{name:<{width}}{len(rows):>6}{agg['turns']:>7}{sum(claims.values()):>8}{sum(flags.values()):>7}"
              f"{entry['share_turns_flagged']:>15.3f}{agg['naive_flags']:>7}{entry['naive_share_turns_flagged']:>13.3f}"
              f"{entry['fabrications_caught'] or 0:>12.3f}{entry['naive_fabrications_caught'] or 0:>7.3f}")
        if name != "ALL":
            records += [r for _, s in rows for r in s["records"]]
    everything = result["by_agent"]["ALL"]["by_reward"]
    print(f"\nturns flagged, successful vs failed tasks: hardfacts {everything['success']['turns_flagged']} vs "
          f"{everything['failure']['turns_flagged']}; naive {everything['success']['naive_turns_flagged']} vs "
          f"{everything['failure']['naive_turns_flagged']}")
    (HERE / "out").mkdir(exist_ok=True)
    with open(HERE / "out" / f"{stem}-flags.jsonl", "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    total = result["by_agent"]["ALL"]
    print(f"flags with a Derivation: {total['share_flags_with_derivation']:.3f}; caught fabrications given one by "
          f"coincidence: {total['share_caught_fabrications_with_derivation']:.3f}")
    print(f"{len(records)} flags → bench/out/{stem}-flags.jsonl")
    if record:
        path = HERE / "results" / f"{stem}-{rev}{'-' + label if label else ''}.json"
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(f"recorded → {path}")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=HERE / "data" / "taubench")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--label", default="", help="suffix for the recorded file, e.g. 'tools'")
    args = ap.parse_args()
    tools = {d: tool_definitions(args.data, d) for d in ("airline", "retail")}
    jobs = []
    for name in FILES:
        runs = json.loads((args.data / f"{name}.json").read_text(encoding="utf-8"))
        jobs += [(name, n, run, tools[domain(name)]) for n, run in enumerate(runs)]
    evaluate(jobs, list(FILES), "tau-bench historical trajectories @ 59a200c", "taubench", args.record, args.label)
    return 0


if __name__ == "__main__":
    sys.exit(main())
