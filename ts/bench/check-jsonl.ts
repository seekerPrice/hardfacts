/**
 * Read {"id", "output", "sources"} lines on stdin; print {"id", "sources", "claims"} lines, where
 * each claim is [kind, text, supported, value, [start, end], evidence, derivation] and every span is converted
 * from UTF-16 units to code points, the unit Python uses. Used by bench/fuzz_differential.py.
 * Integers beyond 2^53 are parsed exactly, as the CLI parses them.
 */

import { readFileSync } from "node:fs";

import { check } from "../src/index.ts";

const exact = (_key: string, value: unknown, context?: { source?: string }) =>
  typeof value === "number" && !Number.isSafeInteger(value) && context?.source && /^-?\d+$/.test(context.source)
    ? BigInt(context.source)
    : value;
const codePoints = (text: string, units: number) => [...text.slice(0, units)].length;

for (const line of readFileSync(0, "utf8").split("\n")) {
  if (!line.trim()) continue;
  const c = JSON.parse(line, exact);
  const report = check(c.output, c.sources);
  const cp = (units: number) => codePoints(c.output, units);
  const claims = report.claims.map((x) => [x.kind, x.text, x.supported, x.value, [cp(x.span[0]), cp(x.span[1])],
    x.evidence.map((e) => [e.source, e.span.map((u) => codePoints(report.sources[e.source], u)), e.text]),
    x.derivation && [x.derivation.expression, x.derivation.operands.map(([a, b]) => [cp(a), cp(b)])]]);
  process.stdout.write(JSON.stringify({ id: c.id, sources: report.sources, claims }) + "\n");
}
