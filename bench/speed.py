"""Time check() per RAGTruth test response, in one process, best of N passes.

    uv run python bench/speed.py [--passes 3]

The per-response time bench/ragtruth.py records is taken on whatever else the machine is doing,
so it moves with load (v0.2's recorded 2.2 ms ran beside eight audit agents). Run this on a quiet
machine, and compare versions in the same sitting: check out the other commit in a worktree and
run the same command there.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from hardfacts import check  # noqa: E402
from ragtruth import HERE  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--passes", type=int, default=3)
    ap.add_argument("--split", default="test")
    args = ap.parse_args()
    data = HERE / "data"
    sources = {json.loads(l)["source_id"]: json.loads(l) for l in (data / "source_info.jsonl").read_text(encoding="utf-8").splitlines()}
    jobs = []
    for line in (data / "response.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["split"] == args.split:
            jobs.append((r["response"], [sources[r["source_id"]]["prompt"]]))
    best = float("inf")
    for _ in range(args.passes):
        start = time.perf_counter()
        for output, seen in jobs:
            check(output, seen)
        best = min(best, time.perf_counter() - start)
    print(f"{len(jobs)} responses, best of {args.passes}: {best / len(jobs) * 1e6:.0f} µs per response")
    return 0


if __name__ == "__main__":
    sys.exit(main())
