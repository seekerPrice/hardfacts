import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const dir = mkdtempSync(join(tmpdir(), "hardfacts-"));
const file = (name: string, text: string | Buffer) => {
  const path = join(dir, name);
  writeFileSync(path, text);
  return path;
};
const run = (...args: string[]) => spawnSync(process.execPath, [fileURLToPath(new URL("../src/cli.ts", import.meta.url)), ...args], { encoding: "utf8" });

test("exit 0 when every claim is supported", () => {
  assert.equal(run("check", file("a.txt", "Delivery in 3 days."), file("s.txt", "Standard delivery: 3 days.")).status, 0);
});

test("exit 1 and the claim is printed when unsupported", () => {
  const r = run("check", file("b.txt", "Delivery in 5 days."), file("s2.txt", "Standard delivery: 3 days."));
  assert.equal(r.status, 1);
  assert.match(r.stdout, /UNSUPPORTED quantity\s+"5"/);
});

test("json sources are parsed and --json prints the report", () => {
  const r = run("check", "--json", file("c.txt", "It weighs 2.5 kg."), file("t.json", '{"weight_kg": 2.5}'));
  assert.equal(r.status, 0);
  assert.equal(JSON.parse(r.stdout).ok, true);
});

test("--kinds limits the check; unknown kinds are a usage error", () => {
  const out = file("d.txt", "Parcel 1Z999AA10123456784 arrives in 5 days.");
  const src = file("s3.txt", "Tracking 1Z999AA10123456784, ETA 3 days.");
  assert.equal(run("check", "--kinds", "identifier,phone", out, src).status, 0);
  assert.equal(run("check", "--kinds", "names", out).status, 2);
});

test("a missing or non-UTF-8 file is a usage error", () => {
  assert.equal(run("check", join(dir, "nope.txt")).status, 2);
  assert.equal(run("check", file("bad.txt", Buffer.from([0xff, 0xfe, 0xfa]))).status, 2);
});

test("integers beyond 2^53 in a .json source stay exact", () => {
  const src = file("big.json", '{"order_id": 1234567890123456789}');
  assert.equal(run("check", file("ok.txt", "Order 1234567890123456789."), src).status, 0);
  assert.equal(run("check", file("bad.txt", "Order 1234567890123456800."), src).status, 1);
});

test("an empty --kinds is a usage error and -h prints usage with exit 0", () => {
  const out = file("k.txt", "Refund RM 99");
  assert.equal(run("check", "--kinds", "", out).status, 2);
  assert.equal(run("-h").status, 0);
});

test("a derivation is printed next to its flag", () => {
  const out = file("k.txt", "The new kettle is $101.12 and yours was $94.80, so you pay $6.32 more.");
  const r = run("check", out, file("k.json", '{"current": 94.8, "new": 101.12}'));
  assert.equal(r.status, 1);
  assert.match(r.stdout, /UNSUPPORTED money\s+"\$6\.32" at 59-64 = \$101\.12 − \$94\.80/);
});
