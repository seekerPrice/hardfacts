# hardfacts MCP server

An MCP tool, `check_hard_facts(draft, sources, kinds?)`, that lets an agent verify its own draft before answering. It returns every number, date, amount, contact detail and ID with no source, plus a correction instruction.

```bash
# Claude Code
claude mcp add hardfacts -- uv run --directory "/path/to/hardfacts" --with "mcp>=2.2" python integrations/mcp/server.py

# tests (in-process client, no subprocess)
uv run --with "mcp>=2.2" --with anyio --with pytest pytest -q integrations/mcp
```

Built on the official MCP Python SDK v2 (`MCPServer`), verified against `mcp` 2.2.0: in-process tests plus a raw JSON-RPC `initialize` / `tools/list` smoke test over stdio. `mcp` is only needed here. The library itself stays dependency-free.

For the tool to help, the sources have to be in the call. Suit it to agents whose inputs are tool results or retrieved documents they can pass back verbatim.
