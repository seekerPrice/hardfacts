#!/usr/bin/env bash
# Every gate the project has, in one command; any failure stops it with a non-zero exit.
#   tools/verify.sh          # needs bench/fetch_ragtruth.sh and bench/fetch_taubench.sh run once
set -euo pipefail
cd "$(dirname "$0")/.."
step() { printf '\n== %s\n' "$*"; }

step "Python tests";          uv run pytest -q
step "Claude Code hook tests"; uv run pytest -q integrations/claude-code
step "MCP server tests";      uv run --with "mcp>=2.2" --with anyio --with pytest pytest -q integrations/mcp
step "conformance fixture";   uv run python bench/export_fixture.py
step "TypeScript";            (cd ts && npx tsc --noEmit && npm test --silent && npm run bundle --silent)
step "release artifacts";     rm -rf dist && uv build -q && uv run python tools/check_dist.py dist
step "RAGTruth train gate";   uv run python bench/gate.py
step "RAGTruth differential"; mkdir -p bench/out && node ts/bench/differential.ts bench/data > bench/out/ts-flags.jsonl \
                                && uv run python bench/differential.py bench/out/ts-flags.jsonl
step "fuzz differential";     uv run python bench/fuzz_differential.py --cases 20000
step "tau-bench differential"; uv run python bench/taubench_differential.py
step "index differential";    uv run python bench/index_differential.py
step "fixture unchanged";     git diff --exit-code --stat ts/test/fixture.json
printf '\nall gates passed\n'
