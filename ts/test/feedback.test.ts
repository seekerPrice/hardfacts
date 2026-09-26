import assert from "node:assert/strict";
import { test } from "node:test";

import { check } from "../src/index.ts";

// Feedback text itself is compared with Python's on every fixture case (conformance.test.ts).
const KETTLE = [{ current: { price: 94.8 }, new: { price: 101.12 } }];
const DRAFT = "It's $101.12 and yours was $94.80, so you pay $6.32 more, on card ending 2692.";
const SOURCES = [...KETTLE, { card: "gift_card_7250692" }];

test("unexplained lists only the values no arithmetic explains", () => {
  const report = check(DRAFT, SOURCES);
  assert.deepEqual(report.unsupported.map((c) => c.text), ["$6.32", "2692"]);
  assert.deepEqual(report.unexplained.map((c) => c.text), ["2692"]);
});

test("a reply with many amounts is still fast", () => {
  let seed = 1;
  const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  const prices = Array.from({ length: 60 }, () => Math.round((10 + rand() * 989) * 100) / 100);
  const output = prices.map((p) => `$${p.toFixed(2)}`).join(" ") + " " + Array.from({ length: 30 }, () => `$${(10 + rand() * 989).toFixed(3)}`).join(" ");
  const t0 = performance.now();
  check(output, [{ prices }]);
  assert.ok(performance.now() - t0 < 100);
});
