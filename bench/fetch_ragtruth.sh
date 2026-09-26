#!/usr/bin/env bash
# Fetch the RAGTruth corpus (MIT licence, ParticleMedia/RAGTruth) into bench/data/.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data
base=https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset
for f in response.jsonl source_info.jsonl; do
  [ -s "data/$f" ] || curl -fsSL "$base/$f" -o "data/$f"
done
echo "RAGTruth ready in bench/data/"
