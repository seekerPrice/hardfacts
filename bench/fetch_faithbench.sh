#!/usr/bin/env bash
# Fetch FaithBench (Vectara, NAACL 2025; CC BY-NC-SA 4.0) into bench/data/faithbench/.
# Downloaded for evaluation only, never redistributed.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data/faithbench
base=https://raw.githubusercontent.com/vectara/FaithBench/main/data_for_release
for i in 1 2 3 4 5 6 7 8 9 10 11 12 14 15 16; do
  [ -s "data/faithbench/batch_$i.json" ] || curl -fsSL "$base/batch_$i.json" -o "data/faithbench/batch_$i.json"
done
echo "FaithBench ready in bench/data/faithbench/"
