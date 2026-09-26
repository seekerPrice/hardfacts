"""Compare the TypeScript port with the Python reference on every RAGTruth response.

    node ts/bench/differential.ts bench/data > bench/out/ts-flags.jsonl
    uv run python bench/differential.py bench/out/ts-flags.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from hardfacts import check

HERE = Path(__file__).parent


def main() -> int:
    ts = {}
    for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        ts[row["id"]] = [tuple(c) for c in row["claims"]]
    sources = {}
    for line in (HERE / "data" / "source_info.jsonl").read_text(encoding="utf-8").splitlines():
        s = json.loads(line)
        sources[s["source_id"]] = s["prompt"]
    same = differ = 0
    for line in (HERE / "data" / "response.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        py = [(c.kind, c.text, c.supported, list(c.span)) for c in check(r["response"], [sources[r["source_id"]]]).claims]
        if py == ts[r["id"]]:
            same += 1
        else:
            differ += 1
            if differ <= 10:
                print(f"[{r['id']}]\n  py: {[c for c in py if c not in ts[r['id']]]}\n  ts: {[c for c in ts[r['id']] if c not in py]}")
    print(f"identical: {same}  different: {differ}  ({same / (same + differ):.2%} identical)")
    return 1 if differ else 0


if __name__ == "__main__":
    sys.exit(main())
