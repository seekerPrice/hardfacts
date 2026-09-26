"""The matching index must never change a Report: indexed check() against the brute-force pairing.

    uv run python bench/index_differential.py

check() visits, for each Claim, only the Evidence sharing a key with it (claim_keys and evidence_keys
in _match.py). Giving every Fact one universal key turns that back into "every Claim against every
piece of Evidence". Both are run on RAGTruth (every response), tau-bench (every 4th run), the fuzz
generator and the recorded conformance cases, and every Report must be identical, Evidence included.
"""

from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import hardfacts._check as checking  # noqa: E402
from fuzz_differential import arithmetic, text  # noqa: E402
from ragtruth import HERE  # noqa: E402
from taubench import FILES, domain, tool_definitions, turns  # noqa: E402

INDEXED = (checking.claim_keys, checking.evidence_keys)


def everything(_fact):
    return {("all",)}


def both(output: str, sources: list) -> tuple[dict, dict]:
    checking.claim_keys, checking.evidence_keys = INDEXED
    fast = checking.check(output, sources).to_dict()
    checking.claim_keys = checking.evidence_keys = everything
    try:
        slow = checking.check(output, sources).to_dict()
    finally:
        checking.claim_keys, checking.evidence_keys = INDEXED
    return fast, slow


def cases():
    data = HERE / "data"
    sources = {json.loads(line)["source_id"]: json.loads(line) for line in (data / "source_info.jsonl").read_text(encoding="utf-8").splitlines()}
    for line in (data / "response.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        yield "ragtruth", r["response"], [sources[r["source_id"]]["prompt"]]
    for name in FILES:
        tools = tool_definitions(data / "taubench", domain(name))
        for n, run in enumerate(json.loads((data / "taubench" / f"{name}.json").read_text(encoding="utf-8"))):
            if n % 4 == 0:
                for _, output, seen in turns(run["traj"], tools):
                    yield "tau-bench", output, seen
    rng = random.Random(0)
    for _ in range(20000):
        if rng.random() < 0.2:
            c = arithmetic(rng)
            yield "fuzz", c["output"], c["sources"]
        else:
            output = text(rng)
            yield "fuzz", output, [output if rng.random() < 0.3 else text(rng) for _ in range(rng.randint(0, 2))]
    for c in json.loads((HERE.parent / "ts" / "test" / "fixture.json").read_text(encoding="utf-8")):
        yield "fixture", c["output"], c["sources"]


def main() -> int:
    counts: dict[str, list[int]] = {}
    for label, output, sources in cases():
        fast, slow = both(output, sources)
        seen = counts.setdefault(label, [0, 0])
        seen[0] += 1
        if fast != slow:
            seen[1] += 1
            if sum(c[1] for c in counts.values()) <= 3:
                print(json.dumps({"output": output[:300], "indexed": fast["claims"], "brute": slow["claims"]}, default=str)[:1500])
    for label, (n, bad) in counts.items():
        print(f"{label:<10} {n - bad}/{n} identical")
    return 1 if any(bad for _, bad in counts.values()) else 0


if __name__ == "__main__":
    sys.exit(main())
