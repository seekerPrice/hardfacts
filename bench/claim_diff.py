"""Every Claim that a change adds, drops or flips, over all of RAGTruth and tau-bench.

    uv run python bench/claim_diff.py [--base HEAD]          # the working tree against a commit

The gates compare the two ports and floor a few aggregate numbers; a rule change can pass them and
still flip hundreds of individual Claims. This checks the base commit out into a temporary git
worktree, runs check() over ~40,000 outputs on both versions, and lists every output whose Claims
differ. Outputs that gain an Unsupported Claim are listed first: those are the possible regressions.
It found three regressions tonight that every gate passed ("1/2 cup" read as a date among them).

Needs bench/fetch_ragtruth.sh and bench/fetch_taubench.sh run once.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DUMP = r'''
import json, sys
from pathlib import Path
bench = Path(sys.argv[1])
sys.path.insert(0, str(bench))
from hardfacts import check
from taubench import FILES, domain, tool_definitions, turns
data = bench / "data"
sources = {json.loads(l)["source_id"]: json.loads(l) for l in (data / "source_info.jsonl").read_text(encoding="utf-8").splitlines()}
out = open(sys.argv[2], "w", encoding="utf-8")
for line in (data / "response.jsonl").read_text(encoding="utf-8").splitlines():
    r = json.loads(line)
    claims = check(r["response"], [sources[r["source_id"]]["prompt"]]).claims
    out.write(json.dumps(["ragtruth/" + r["id"], [(c.kind, c.text, c.supported) for c in claims]]) + "\n")
for name in FILES:
    tools = tool_definitions(data / "taubench", domain(name))
    for n, run in enumerate(json.loads((data / "taubench" / f"{name}.json").read_text(encoding="utf-8"))):
        for i, (_, output, seen) in enumerate(turns(run["traj"], tools)):
            claims = check(output, seen).claims
            out.write(json.dumps([f"taubench/{name}/{n}/{i}", [(c.kind, c.text, c.supported) for c in claims]]) + "\n")
'''


def dump(tree: Path, out: Path) -> dict[str, set]:
    script = out.with_suffix(".py")
    script.write_text(DUMP, encoding="utf-8")
    subprocess.run(["uv", "run", "--quiet", "--project", str(tree), "python", str(script), str(ROOT / "bench"), str(out)],
                   cwd=tree, check=True, env=None)
    return {k: set(map(tuple, v)) for k, v in (json.loads(line) for line in out.read_text(encoding="utf-8").splitlines())}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="HEAD", help="the commit to compare the working tree against")
    ap.add_argument("--show", type=int, default=30, help="how many changed outputs to print")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        base = tmp / "base"
        subprocess.run(["git", "worktree", "add", "--quiet", "--detach", str(base), args.base], cwd=ROOT, check=True)
        try:
            old = dump(base, tmp / "old.jsonl")
        finally:
            subprocess.run(["git", "worktree", "remove", "--force", str(base)], cwd=ROOT, check=True)
        new = dump(ROOT, tmp / "new.jsonl")
    changed = [k for k in new if new[k] != old.get(k)]
    regressions = [k for k in changed if any(not c[2] for c in new[k] - old.get(k, set()))]
    for k in sorted(changed, key=lambda k: (k not in regressions, k))[:args.show]:
        print(("NEW UNSUPPORTED " if k in regressions else "changed         ") + k)
        print("   was:", sorted(old.get(k, set()) - new[k])[:4])
        print("   now:", sorted(new[k] - old.get(k, set()))[:4])
    print(f"\n{len(changed)} of {len(new)} outputs changed; {len(regressions)} gained an Unsupported Claim")
    return 1 if regressions else 0


if __name__ == "__main__":
    sys.exit(main())
