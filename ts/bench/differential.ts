/**
 * Differential test: run the TypeScript port over every RAGTruth response and write
 * one JSON line of flags per response, for bench/differential.py to compare with
 * the Python reference.
 *
 *   node ts/bench/differential.ts bench/data > bench/out/ts-flags.jsonl
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";

import { check } from "../src/index.ts";

const data = process.argv[2] ?? "bench/data";
const sources = new Map<string, string>();
for (const line of readFileSync(join(data, "source_info.jsonl"), "utf8").split("\n")) {
  if (!line.trim()) continue;
  const s = JSON.parse(line);
  sources.set(s.source_id, s.prompt);
}
let elapsed = 0;
let n = 0;
for (const line of readFileSync(join(data, "response.jsonl"), "utf8").split("\n")) {
  if (!line.trim()) continue;
  const r = JSON.parse(line);
  const t0 = performance.now();
  const report = check(r.response, [sources.get(r.source_id)!]);
  elapsed += performance.now() - t0;
  n++;
  const cp = (units: number) => [...r.response.slice(0, units)].length; // UTF-16 units → code points, as Python counts
  process.stdout.write(JSON.stringify({ id: r.id, claims: report.claims.map((c) => [c.kind, c.text, c.supported, [cp(c.span[0]), cp(c.span[1])]]) }) + "\n");
}
process.stderr.write(`${n} responses, ${(elapsed / n * 1000).toFixed(1)} µs/response\n`);
