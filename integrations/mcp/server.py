"""hardfacts as an MCP tool, so an agent can check its own draft before it answers.

    claude mcp add hardfacts -- uv run --directory "<path to this repo>" --with "mcp>=2.2" python integrations/mcp/server.py

Any MCP client works (Claude Code, Claude Desktop, Cursor). The agent passes its draft and
the material it was given; the tool returns every hard fact with no source, plus a
correction instruction it can follow before replying.
"""

from __future__ import annotations

from typing import Any, TypedDict

from mcp.server.mcpserver import MCPServer

from hardfacts import KINDS, check, feedback

server = MCPServer("hardfacts")


class UnsupportedFact(TypedDict):
    kind: str
    text: str
    start: int
    end: int
    computed_as: str | None
    """Arithmetic over the draft's own supported values that gives this value ("$101.12 − $94.80"), if any."""


class FactCheck(TypedDict):
    ok: bool
    """Every hard fact has a source."""
    ok_except_calculations: bool
    """Every hard fact has a source or is shown arithmetic on the draft's own supported values."""
    hard_facts: int
    unsupported: list[UnsupportedFact]
    feedback: str


@server.tool()
def check_hard_facts(draft: str, sources: list[Any], kinds: list[str] | None = None) -> FactCheck:
    """Check every number, date, time, amount, percentage, phone number, email, URL and ID in
    `draft` against `sources` (the documents, tool results or records you were given; strings
    or JSON objects). Returns the values no source contains. Call it before sending any answer
    that states such values, and rewrite until `ok` is true.

    `kinds` optionally limits the check, e.g. ["identifier", "money", "date"]. When an answer must
    contain a calculation (a total, a price difference), `computed_as` shows the working the tool
    found for it; check those operands, and stop when `ok_except_calculations` is true.
    """
    if kinds is not None and not set(kinds) <= KINDS:
        raise ValueError(f"unknown kinds {sorted(set(kinds) - KINDS)}; choose from {sorted(KINDS)}")
    report = check(draft, sources, kinds=kinds)
    return {
        "ok": report.ok,
        "ok_except_calculations": not report.unexplained,
        "hard_facts": len(report.claims),
        "unsupported": [{"kind": c.kind, "text": c.text, "start": c.span[0], "end": c.span[1],
                         "computed_as": c.derivation.expression if c.derivation else None} for c in report.unsupported],
        "feedback": feedback(report),
    }


if __name__ == "__main__":
    server.run("stdio")
