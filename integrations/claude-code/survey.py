"""How often would the Stop hook fire on your own sessions? Counts only; no content is printed or kept.

    uv run python integrations/claude-code/survey.py ~/.claude/projects --sessions 60 [--seed 0]

Replays each sampled transcript turn by turn: the transcript is cut just before every prompt you
typed, and the hook's own reader and default Kinds decide whether that turn's answer states a value
none of the session's Sources contain (report.unexplained, as the hook uses). Prints the share of
turns the hook would have warned on, and the Kinds involved.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import hardfacts_stop_hook as hook  # noqa: E402
import transcript  # noqa: E402

from hardfacts import KINDS, check  # noqa: E402


def turns(path: Path):
    """Each point in the transcript where one of your prompts starts the next turn."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    cuts = []
    for n, line in enumerate(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if isinstance(entry, dict) and transcript._is_prompt(entry) and n:
            cuts.append(n)
    cuts.append(len(lines))
    for cut in cuts:
        yield lines[:cut]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="a folder of Claude Code transcripts (*.jsonl), searched recursively")
    ap.add_argument("--sessions", type=int, default=60)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    kinds = {k.strip() for k in os.environ.get("HARDFACTS_HOOK_KINDS", hook.DEFAULT_KINDS).split(",") if k.strip()} & KINDS
    paths = sorted(p for p in args.root.expanduser().rglob("*.jsonl")
                   if p.stat().st_size > 0 and "subagents" not in p.parts and not p.name.startswith("agent-"))
    # the hook stops your sessions; subagents' transcripts (most of the files) are not its turns
    random.Random(args.seed).shuffle(paths)
    total = warned = 0
    by_kind: Counter = Counter()
    with tempfile.TemporaryDirectory() as tmp:
        cut_file = Path(tmp) / "turn.jsonl"
        for path in paths[:args.sessions]:
            for lines in turns(path):
                cut_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
                answer, sources = transcript.read(cut_file)
                if not answer:
                    continue
                total += 1
                unexplained = check(answer, sources, kinds=kinds).unexplained
                if unexplained:
                    warned += 1
                    by_kind.update({c.kind for c in unexplained})
    print(json.dumps({"sessions": min(args.sessions, len(paths)), "turns_with_an_answer": total,
                      "turns_the_hook_would_warn_on": warned,
                      "share": round(warned / total, 4) if total else None,
                      "turns_by_kind": dict(by_kind.most_common())}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
