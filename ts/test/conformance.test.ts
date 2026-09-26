/**
 * The TypeScript port must reproduce the Python reference exactly.
 * test/fixture.json is every check() the Python suite makes, with its Report
 * (regenerate with `uv run python bench/export_fixture.py` from the repo root).
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { check, feedback, toJSON } from "../src/index.ts";

interface Case {
  test: string;
  output: string;
  sources: unknown[];
  kinds: string[] | null;
  report: ReturnType<typeof toJSON>;
  feedback: string;
}

const cases: Case[] = JSON.parse(readFileSync(new URL("./fixture.json", import.meta.url), "utf8"));

/** TS spans count UTF-16 units and Python's count code points; compare in code points. */
function inCodePoints(report: ReturnType<typeof toJSON>, output: string): ReturnType<typeof toJSON> {
  const cp = (text: string, [a, b]: [number, number]): [number, number] => [[...text.slice(0, a)].length, [...text.slice(0, b)].length];
  return {
    ...report,
    unsupported: report.unsupported.map((c) => ({ ...c, span: cp(output, c.span) })),
    claims: report.claims.map((c) => ({
      ...c,
      span: cp(output, c.span),
      evidence: c.evidence.map((e) => ({ ...e, span: cp(report.sources[e.source], e.span) })),
    })),
  };
}

for (const [i, c] of cases.entries()) {
  test(`${i} ${c.test}`, () => {
    const report = check(c.output, c.sources, c.kinds ? { kinds: c.kinds } : {});
    assert.deepEqual(inCodePoints(toJSON(report), c.output), c.report); // rendered Sources and Evidence spans included
    assert.equal(feedback(report), c.feedback);
  });
}
