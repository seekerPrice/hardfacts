"""Measure, before building: how often do agents pair a weekday with a date, and get it wrong?

    uv run python bench/weekday_experiment.py

"Friday, October 3" passes against "Wednesday, October 3", because weekdays aren't read. This
scans every tau-bench and tau2-bench agent turn for a weekday next to a full date (a stated year, or
the conversation's current year from the tool results) and checks it against the calendar.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from hardfacts import check  # noqa: E402

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
NEAR = re.compile(r"\b(" + "|".join(DAYS) + r")\b,?\s*(?:the\s+)?$", re.I)
AFTER = re.compile(r"^\s*\(?\s*(" + "|".join(DAYS) + r")\b", re.I)


def main() -> int:
    seen = paired = wrong = 0
    examples = []
    from taubench import FILES, domain, tool_definitions, turns
    data = HERE / "data"
    outputs = []
    for name in FILES:
        tools = tool_definitions(data / "taubench", domain(name))
        for run in json.loads((data / "taubench" / f"{name}.json").read_text(encoding="utf-8")):
            outputs += [text for _, text, _ in turns(run["traj"], tools)]
    from tau2bench import RUNS, trajectory
    for run_name in RUNS:
        d = json.loads((data / "tau2" / f"{run_name}.json").read_text(encoding="utf-8"))
        policy = d["info"]["environment_info"]["policy"]
        for sim in d["simulations"]:
            outputs += [m["content"] for m in trajectory(sim, policy) if m["role"] == "assistant" and m.get("content")]
    for text in outputs:
        for c in check(text, []).claims:
            if c.kind != "date":
                continue
            seen += 1
            before, after = text[max(0, c.span[0] - 14):c.span[0]], text[c.span[1]:c.span[1] + 14]
            m = NEAR.search(before) or AFTER.search(after)
            if not m:
                continue
            full = [r for r in c.value if "X" not in r]
            if not full:
                continue
            paired += 1
            y, mo, d = map(int, full[0].split("-"))
            actual = DAYS[dt.date(y, mo, d).weekday()]
            if m.group(1).lower() != actual:
                wrong += 1
                if len(examples) < 10:
                    examples.append(f"{m.group(1)} {c.text} (really {actual.title()})")
    print(json.dumps({"agent_turns": len(outputs), "dates": seen, "weekday_with_full_date": paired,
                      "weekday_wrong": wrong, "examples": examples}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
