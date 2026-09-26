"""Read a Claude Code session transcript (JSONL) into hardfacts' Output and Sources.

The Output is the text Claude wrote in the current turn, after the user's last real prompt. The
Sources are everything Claude was shown in the session: tool results, the prompts the user typed,
system notices (task notifications, agents' hand-backs) and attachments (hook output, queued
prompts). A value in the answer that none of them contains came from nowhere the session can show.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

LARGEST_SOURCES = 8_000_000
"""Characters of Sources kept, newest first. Reading them costs about 1 s per million characters,
so this caps a turn's check near 8 s; a session with 2.4 MB of Sources takes 2.3 s."""


def _entries(path: Path) -> Iterator[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and (isinstance(entry.get("message"), dict) or entry.get("type") == "attachment"):
                yield entry


def _blocks(entry: dict[str, Any]) -> list[dict[str, Any]]:
    content = entry["message"].get("content")
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return [b for b in content or [] if isinstance(b, dict)]


def _tool_result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    return "\n".join(part.get("text", "") for part in content or [] if isinstance(part, dict))


def _is_prompt(entry: dict[str, Any]) -> bool:
    """A prompt the user typed: a user entry with text, not a tool result or a system injection."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    blocks = _blocks(entry)
    return bool(blocks) and all(b.get("type") == "text" for b in blocks)


def read(path: str | Path) -> tuple[str, list[str]]:
    """(the current turn's answer, the session's Sources)."""
    entries = [e for e in _entries(Path(path)) if not e.get("isSidechain")]
    last_prompt = max((i for i, e in enumerate(entries) if _is_prompt(e)), default=-1)
    turn = [e for e in entries[last_prompt + 1:] if "message" in e]
    answer = "\n\n".join(b.get("text", "") for e in turn if e.get("type") == "assistant"
                         for b in _blocks(e) if b.get("type") == "text")
    sources: list[str] = []
    for e in entries:
        if e.get("type") == "attachment":
            sources.append(json.dumps(e.get("attachment"), ensure_ascii=False))
        elif e.get("type") == "user":
            for b in _blocks(e):
                if b.get("type") == "tool_result":
                    sources.append(_tool_result_text(b))
                elif b.get("type") == "text":  # a prompt, or a notice Claude was shown
                    sources.append(b.get("text", ""))
    kept, size = [], 0
    for text in reversed(sources):
        if size + len(text) > LARGEST_SOURCES:
            break
        kept.append(text)
        size += len(text)
    return answer, kept[::-1]
