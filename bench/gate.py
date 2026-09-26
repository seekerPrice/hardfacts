"""Fail loudly if a change makes hardfacts worse on RAGTruth train.

    uv run python bench/gate.py

Thresholds sit just below the numbers recorded at the v0.1 release (train split,
commit 78413c9), so a regression fails CI rather than slipping into a release.
Lower a threshold only in a commit that says why.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import fault_injection  # noqa: E402
import ragtruth  # noqa: E402

GATES = {
    "train span precision": 0.70,        # release: 0.718
    "train hard-fact recall": 0.52,      # release: 0.544
    "fabrications caught": 0.93,         # release: 0.946
}
MAX_CLEAN_FLAG_RATE = 0.03               # release: 0.021


def main() -> int:
    data = ragtruth.HERE / "data"
    t = ragtruth.run("train", data, None, 0)["hardfacts"]["ALL"].metrics()
    f = fault_injection.run("train", data, 0)
    caught = sum(f["caught"][("hardfacts", "fabricate")].values()) / sum(f["planted"]["fabricate"].values())
    tasks = ("QA", "Summary", "Data2txt")
    clean = sum(f["clean_flagged"][("hardfacts", k)] for k in tasks) / sum(f["clean_total"][("hardfacts", k)] for k in tasks)
    measured = {"train span precision": t["span_precision"], "train hard-fact recall": t["hard_fact_recall"],
                "fabrications caught": caught}
    failed = False
    for name, floor in GATES.items():
        ok = measured[name] >= floor
        failed |= not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {measured[name]:.3f} (floor {floor})")
    ok = clean <= MAX_CLEAN_FLAG_RATE
    failed |= not ok
    print(f"{'PASS' if ok else 'FAIL'}  clean responses flagged: {clean:.3f} (ceiling {MAX_CLEAN_FLAG_RATE})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
