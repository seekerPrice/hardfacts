/** Port-only behaviour the shared fixture can't express (it is recorded from Python). */

import assert from "node:assert/strict";
import { test } from "node:test";

import { check, render } from "../src/index.ts";

test("line anchors follow Python: only \\n starts a line, not \\r or U+2028", () => {
  const lone = check("Steps:\r1. Preheat to 400°F.", ["Preheat to 400°F"]);
  assert.deepEqual(lone.claims.map((c) => c.text), ["1", "400°F"]);
});

test("a letter from outside the BMP counts as a letter before a number word", () => {
  assert.deepEqual(check("𝐀ten items", ["10 items"]).claims.map((c) => c.text), []);
});

test("numbers render in plain decimal notation, as the Python reference does", () => {
  assert.equal(render({ rate: 0.00005, cap: 1e21, n: -1.5e-7 }), '{"rate": 0.00005, "cap": 1000000000000000000000, "n": -0.00000015}');
});

test("a bare string as sources is a TypeError", () => {
  assert.throws(() => check("RM 45", "refund RM 45" as unknown as unknown[]), TypeError);
});
