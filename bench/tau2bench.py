"""hardfacts on tau2-bench: a held-out test of everything tau-bench taught it.

    bench/fetch_tau2bench.sh
    uv run python bench/tau2bench.py --record
    uv run python bench/tau2bench.py --record --label postfix   # after a fix: not out-of-sample

Every rule added after the first tau-bench run came from reading tau-bench flags, so tau-bench
can no longer say whether they generalise. tau2-bench (Sierra, MIT) publishes runs of newer agents
(Claude 3.7 Sonnet, GPT-4.1, GPT-4.1-mini, o4-mini) in airline, retail and a new telecom domain.
Pre-registered in docs/reviews/2026-09-26-tau2bench-preregistration.md: the checker, files and
metrics are fixed before the first score, and the run is scored once.

The method is bench/taubench.py's. Each assistant turn with text is an Output. Its Sources are
the domain's tool definitions (tools.py, whose docstrings the agents saw as schemas), the policy,
the user's turns and the tool results the agent requested. In telecom the user also runs tools on
their own phone; the agent never sees those results, so they are not Sources.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ragtruth import HERE  # noqa: E402
from taubench import evaluate  # noqa: E402

RUNS = [
    f"{model}_{domain}_{setting}_gpt-4.1-2025-04-14_4trials"
    for model, setting in (("claude-3-7-sonnet-20250219", "default"), ("gpt-4.1-2025-04-14", "default"),
                           ("gpt-4.1-mini-2025-04-14", "base"), ("o4-mini-2025-04-16", "default"))
    for domain in ("airline", "retail", "telecom")
]


def label(run: str) -> str:
    model, domain = run.split("_")[:2]
    return f"{model.rsplit('-2025', 1)[0]}/{domain}"


def trajectory(simulation: dict, policy: str) -> list[dict]:
    """tau2's messages in tau-bench's shape, keeping only what the agent was shown."""
    traj = [{"role": "system", "content": policy}]
    for m in simulation.get("messages") or []:
        if m.get("role") == "tool" and m.get("requestor") != "assistant":
            continue  # the user's own device tools: the agent never sees their results
        traj.append({"role": m.get("role"), "content": m.get("content")})
    return traj


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=HERE / "data" / "tau2")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--label", default="", help='e.g. "postfix": any run after the held-out one')
    args = ap.parse_args()
    commit = (args.data / "COMMIT").read_text(encoding="utf-8").strip()[:7]
    jobs, names = [], []
    for run in RUNS:
        data = json.loads((args.data / f"{run}.json").read_text(encoding="utf-8"))
        env = data["info"]["environment_info"]
        tools = (args.data / "tools" / f"{env['domain_name']}.py").read_text(encoding="utf-8")
        name = label(run)
        names.append(name)
        for n, sim in enumerate(data["simulations"]):
            reward = (sim.get("reward_info") or {}).get("reward")
            jobs.append((name, n, {"traj": trajectory(sim, env["policy"]), "reward": reward}, tools))
    evaluate(jobs, names, f"tau2-bench published runs @ {commit}", "tau2bench", args.record, args.label)
    return 0


if __name__ == "__main__":
    sys.exit(main())
