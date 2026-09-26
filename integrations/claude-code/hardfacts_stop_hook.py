"""A Claude Code Stop hook: before Claude finishes a turn, check its answer's hard facts against the session.

Every number, amount, date, ID, phone, email and URL in the answer is checked against what the
session actually showed Claude: the tool results and your prompts. When a value appears in none of
them and isn't arithmetic on the answer's own supported values, the hook asks Claude to verify it
or say where it came from, once per turn.

Configure (see README.md): HARDFACTS_HOOK_KINDS (comma-separated Kinds, default below) and
HARDFACTS_HOOK_MODE ("warn", the default, only shows you the values; "block" asks Claude to fix the answer).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from transcript import read  # noqa: E402

from hardfacts import KINDS, check  # noqa: E402
from hardfacts._kinds import KIND_NAMES  # noqa: E402

DEFAULT_KINDS = "identifier,money,percent,phone,email,url,date"
"""Plain quantities are left out by default: in coding sessions Claude counts things ("3 files",
"12 tests") far more often than it quotes them."""
SHOWN = 12
"""Unsupported values listed in one message; the rest are counted."""


def message(unexplained) -> str:
    lines = [f'- "{c.text}" ({KIND_NAMES.get(c.kind, c.kind)})' for c in unexplained[:SHOWN]]
    more = f"\n- …and {len(unexplained) - SHOWN} more" if len(unexplained) > SHOWN else ""
    return (
        "hardfacts: your answer states values that no tool result or user message in this session contains:\n"
        + "\n".join(lines) + more
        + "\nCheck each one. If it came from a tool, quote it exactly; if you computed or rounded it, say so; "
        "if you can't source it, remove it or say it is unverified."
    )


def main() -> int:
    event = json.load(sys.stdin)
    if event.get("stop_hook_active"):
        return 0  # this turn already continued once because of a Stop hook: never loop
    kinds = {k.strip() for k in os.environ.get("HARDFACTS_HOOK_KINDS", DEFAULT_KINDS).split(",") if k.strip()} & KINDS
    turn, sources = read(event["transcript_path"])
    # the transcript is written asynchronously, so the final message may not be in it yet
    answer = event.get("last_assistant_message") or turn
    if not answer.strip():
        return 0
    report = check(answer, sources, kinds=kinds)
    if not report.unexplained:
        return 0
    text = message(report.unexplained)
    if os.environ.get("HARDFACTS_HOOK_MODE", "warn") != "block":
        print(json.dumps({"systemMessage": text}))  # shown to you; Claude stops as usual
        return 0
    print(text, file=sys.stderr)
    return 2  # documented for Stop: "prevents Claude from stopping, continues the conversation"


if __name__ == "__main__":
    sys.exit(main())
