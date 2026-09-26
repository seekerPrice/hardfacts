# hardfacts as a Claude Code Stop hook

Before Claude finishes a turn, this hook checks the answer against the session. Every ID, amount, percentage, date, phone number, email and URL in the answer is looked for in what Claude was actually shown: the tool results (file reads, command output, API responses) and your prompts.
- A value found in none of them, that isn't arithmetic on the answer's own supported values, is listed for you (the default).
- In block mode it stops Claude once with the list, so Claude can quote the source, say it computed or rounded the value, or drop it. It never blocks twice in one turn.
- It makes no model calls. On a long session (a 14 MB transcript, 2.4 MB of Sources) it takes 2.3 s per turn, almost all of it reading the Sources. The Sources are capped at 8 million characters, which puts the worst case around 8 s.

Nothing has been installed. This is opt-in.

## Install

Add to `~/.claude/settings.json` (every project) or a project's `.claude/settings.json`, with the path pointing at your copy of this repository:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "uv run --directory \"/path/to/hardfacts\" python integrations/claude-code/hardfacts_stop_hook.py",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Settings:
- **It only warns by default.** It shows you the list and lets Claude stop. Set `HARDFACTS_HOOK_MODE=block` to make Claude answer the list first. That's worth it for work where the values go to other people; see the measurements below.
- **Choose which Kinds are checked** with `HARDFACTS_HOOK_KINDS` (comma-separated). The default is `identifier,money,percent,phone,email,url,date`. Plain quantities are left out because Claude counts things ("3 files", "12 tests") far more often than it quotes them.

## How it decides

- The **answer** is the final assistant message: `last_assistant_message` from the hook's input, or the transcript's last text if that field is absent.
- The **Sources** are every tool result, prompt, notice and attachment in the session. The newest 8 million characters are kept.
- It **blocks** by exiting 2 with the list on stderr. For a Stop hook, exit 2 "prevents Claude from stopping, continues the conversation" (the Claude Code hooks reference).
- In **warn** mode it returns `systemMessage` instead.

## What it finds, measured on real sessions

It was run, read-only and counting only, over a random 60 of the maintainer's Claude Code sessions (1,318 turns). The survey found three gaps, and each is now fixed:
- **Sources the reader skipped.** Task notifications, agents' hand-backs and hook output weren't read.
- **Markdown around URLs.** `**https://…/637**` didn't equal the Source's link.
- **Numbers inside URLs, and git hashes.** "PR #3337" wasn't read from a tool's `…/pull/3337`, and short and full hashes didn't match.

Fixing them cut the share of turns the hook would stop from 36% to **16%**, with the default Kinds. What remains is mostly:
- IDs Claude truncates with an ellipsis (a key shortened to its first characters and "..."), which a checker can't match exactly
- URLs Claude brought from a web search or its own knowledge
- values from more than 8 MB back in a very long session

**That's why warn is the default.** A block on one turn in six is too often for coding sessions. For work that states amounts, dates or contact details to other people, narrow the Kinds (`HARDFACTS_HOOK_KINDS=money,percent,date,phone,email`) and block.

On the session that built hardfacts, one long turn had 134 hard facts across all Kinds. The hook flagged 5, and all 5 were values Claude had **rounded or unit-converted** from real tool output (`0.0131 s` as `0.013 s`, `13486872` as `13.5M`). A "rounded from" explanation was measured and rejected (ADR-0007): it explains too few flags on the benchmarks to justify the coincidences it adds.

## Tests

```bash
uv run pytest -q integrations/claude-code
```
