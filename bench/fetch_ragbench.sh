#!/usr/bin/env bash
# RAGBench (Galileo, CC BY 4.0): test splits of all 12 subsets, pinned to one dataset revision.
set -euo pipefail
cd "$(dirname "$0")"
REV=97808f3e5fd16ede40bbff6c2949af8139b2eb7b
OUT=data/ragbench
mkdir -p "$OUT"
for s in covidqa cuad delucionqa emanual expertqa finqa hagrid hotpotqa msmarco pubmedqa tatqa techqa; do
  curl -sSLf -o "$OUT/$s-test.parquet" "https://huggingface.co/datasets/galileo-ai/ragbench/resolve/$REV/$s/test-00000-of-00001.parquet"
done
echo "$REV" > "$OUT/REVISION"
ls -la "$OUT"
