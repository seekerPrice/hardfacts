"""uv run pytest -q integrations/claude-code"""

import json
import os
import subprocess
import sys
from pathlib import Path

HOOK = Path(__file__).parent / "hardfacts_stop_hook.py"


def entry(kind, content, **extra):
    role = "assistant" if kind == "assistant" else "user"
    return {"type": kind, "message": {"role": role, "content": content}, **extra}


def transcript(tmp_path, answer):
    lines = [
        entry("user", "What's the status of my order?"),
        entry("assistant", [{"type": "tool_use", "id": "t1", "name": "get_order", "input": {}}]),
        entry("user", [{"type": "tool_result", "tool_use_id": "t1",
                        "content": json.dumps({"order_id": "ORD-2024-0012", "total": 45.5, "eta": "2026-10-03"})}]),
        entry("user", [{"type": "text", "text": "<system-reminder>ignore</system-reminder>"}], isMeta=True),
        entry("assistant", [{"type": "text", "text": answer}]),
    ]
    path = tmp_path / "session.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    return path


def run(path, mode="block", active=False, last=None):
    env = {k: v for k, v in os.environ.items() if k != "HARDFACTS_HOOK_MODE"}
    env |= {"HARDFACTS_HOOK_MODE": mode} if mode else {}
    event = {"session_id": "s", "transcript_path": str(path), "hook_event_name": "Stop", "stop_hook_active": active,
             **({"last_assistant_message": last} if last else {})}
    return subprocess.run([sys.executable, str(HOOK)], input=json.dumps(event), capture_output=True, text=True, env=env)


def test_an_invented_order_id_blocks_the_stop_with_a_reason(tmp_path):
    done = run(transcript(tmp_path, "Order ORD-2024-0013 ($45.50) arrives 3 October."))
    assert done.returncode == 2 and '"ORD-2024-0013"' in done.stderr and "$45.50" not in done.stderr


def test_a_supported_answer_stops_normally(tmp_path):
    done = run(transcript(tmp_path, "Order ORD-2024-0012 ($45.50) arrives 3 October."))
    assert (done.returncode, done.stdout, done.stderr) == (0, "", "")


def test_it_never_blocks_twice_in_one_turn(tmp_path):
    assert run(transcript(tmp_path, "Order ORD-2024-0013 arrives."), active=True).returncode == 0


def test_warn_mode_only_shows_the_values_and_is_the_default(tmp_path):
    for mode in ("warn", None):
        done = run(transcript(tmp_path, "Order ORD-2024-0013 arrives."), mode=mode)
        assert done.returncode == 0 and "ORD-2024-0013" in json.loads(done.stdout)["systemMessage"]


def test_the_final_message_from_the_event_wins_over_a_lagging_transcript(tmp_path):
    done = run(transcript(tmp_path, "Order ORD-2024-0012 arrives."), last="Correction: order ORD-2024-0099.")
    assert done.returncode == 2 and "ORD-2024-0099" in done.stderr


def test_notices_and_attachments_count_as_what_claude_was_shown(tmp_path):
    lines = [
        entry("user", "Open the PR."),
        entry("user", [{"type": "text", "text": "<task-notification>PR #3447 opened: https://github.com/o/r/pull/3447</task-notification>"}], isMeta=True),
        {"type": "attachment", "attachment": {"type": "hook_success", "stdout": "deploy run 34446515834 queued"}},
        entry("assistant", [{"type": "text", "text": "Opened https://github.com/o/r/pull/3447; deploy run 34446515834 is queued."}]),
    ]
    path = tmp_path / "s.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")
    done = run(path)
    assert (done.returncode, done.stderr) == (0, "")
