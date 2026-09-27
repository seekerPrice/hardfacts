#!/usr/bin/env bash
# Fetch tau2-bench's published agent runs (Sierra, MIT) into bench/data/tau2/: one default run per
# model and domain (Claude 3.7 Sonnet, GPT-4.1, GPT-4.1-mini, o4-mini × airline, retail, telecom),
# plus each domain's tools.py (the tool definitions the agents were given). Pinned to one commit.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data/tau2/tools
sha=b7ea9074c1cba482b30687fecdb5c8425fd6f619
base=https://raw.githubusercontent.com/sierra-research/tau2-bench/$sha
for run in \
  claude-3-7-sonnet-20250219_{airline,retail,telecom}_default \
  gpt-4.1-2025-04-14_{airline,retail,telecom}_default \
  gpt-4.1-mini-2025-04-14_{airline,retail,telecom}_base \
  o4-mini-2025-04-16_{airline,retail,telecom}_default; do
  f="${run}_gpt-4.1-2025-04-14_4trials.json"
  [ -s "data/tau2/$f" ] || curl -fsSL --retry 4 --retry-all-errors "$base/data/tau2/results/final/$f" -o "data/tau2/$f"
done
for domain in airline retail telecom; do
  [ -s "data/tau2/tools/$domain.py" ] || curl -fsSL --retry 4 --retry-all-errors "$base/src/tau2/domains/$domain/tools.py" -o "data/tau2/tools/$domain.py"
done
echo "tau2-bench runs ready in bench/data/tau2/"
