"""Measure, before building: would date-difference Derivations help?

    uv run python bench/date_diff_experiment.py

A support agent writes "your 5-day trip (May 20 to May 25)" or "that's 3 nights". The 5 is Unsupported,
and no Derivation explains it, because ADR-0007's search covers amounts, not dates. This counts the
flagged numbers that sit right before "day(s)/night(s)" in tau-bench and tau2-bench replies, and how
many two full dates stated in the same reply explain: their difference, or the difference plus one
(an inclusive count of days).

It also reports coincidence: change the flagged number by one, which a fabrication might do, and
count how often some date pair still "explains" it.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import re
import sys
from pathlib import Path

from hardfacts import check

HERE = Path(__file__).parent
UNIT = re.compile(r"\s*-?\s*(?:days?|nights?)\b", re.I)


def dates(output: str) -> list[dt.date]:
    found = []
    for c in check(output, []).claims:
        if c.kind != "date":
            continue
        for reading in c.value:
            y, m, d = reading.split("-")
            if "X" not in reading:
                try:
                    found.append(dt.date(int(y), int(m), int(d)))
                except ValueError:
                    pass
    return sorted(set(found))


def explains(n: int, ds: list[dt.date]) -> bool:
    return any(abs((b - a).days) in (n, n - 1) for a, b in itertools.combinations(ds, 2))


def main() -> int:
    total = explained = coincidence = 0
    examples = []
    for name in ("taubench-flags.jsonl", "tau2bench-flags.jsonl"):
        for line in (HERE / "out" / name).read_text(encoding="utf-8").splitlines():
            f = json.loads(line)
            if f["kind"] != "quantity" or f["derivation"] or not f["text"].isdigit():
                continue
            if not UNIT.match(f["output"], f["span"][1]):
                continue
            n = int(f["text"])
            ds = dates(f["output"])
            total += 1
            if explains(n, ds):
                explained += 1
                if len(examples) < 8:
                    a = f["output"]
                    examples.append(a[max(0, f["span"][0] - 80):f["span"][1] + 20].replace("\n", " "))
            coincidence += any(explains(m, ds) for m in (n - 1, n + 1) if m > 0) and not explains(n, ds)
    print(json.dumps({"day_counts_flagged": total, "explained_by_two_dates": explained,
                      "explained_share": round(explained / total, 4) if total else None,
                      "off_by_one_fabrication_explained_instead": coincidence, "examples": examples}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
