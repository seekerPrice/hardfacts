"""The TypeScript port against the Python reference on real support-agent turns (tau-bench).

    uv run python bench/taubench_differential.py --turns 3000

Fuzzed text rarely holds a real total or price difference, so Derivations get little fuzz
coverage. tau-bench turns are full of them. A seeded sample of turns, with every Source the
agent had seen, goes through both ports and must match exactly (bench/fuzz_differential.py).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fuzz_differential import compare  # noqa: E402
from ragtruth import HERE  # noqa: E402
from taubench import FILES, domain, tool_definitions, turns  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--data", type=Path, default=HERE / "data" / "taubench")
    args = ap.parse_args()
    everything = []
    for name in FILES:
        tools = tool_definitions(args.data, domain(name))
        for run in json.loads((args.data / f"{name}.json").read_text(encoding="utf-8")):
            everything += [(text, sources) for _, text, sources in turns(run["traj"], tools)]
    picked = random.Random(args.seed).sample(everything, min(args.turns, len(everything)))
    cases = [{"id": i, "output": text, "sources": sources} for i, (text, sources) in enumerate(picked)]
    bad = compare(cases)
    print(f"{len(cases) - bad}/{len(cases)} tau-bench turns identical")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
