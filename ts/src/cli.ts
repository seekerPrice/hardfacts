#!/usr/bin/env node
/**
 * hardfacts check OUTPUT [SOURCE ...] [--json] [--kinds a,b]
 *
 * Exit status: 0 when every Claim is Supported, 1 when any is Unsupported, 2 on a usage error.
 */

import { readFileSync } from "node:fs";
import { parseArgs } from "node:util";

import { check, KINDS, toJSON } from "./index.ts";

function read(path: string): string {
  const bytes = readFileSync(path === "-" ? 0 : path);
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

function loadSource(path: string): unknown {
  const text = read(path);
  if (!path.endsWith(".json")) return text;
  try {
    // Integers beyond 2^53 (order IDs) stay exact as BigInt, read from the source text
    return JSON.parse(text, (_key, value, context?: { source?: string }) =>
      typeof value === "number" && !Number.isSafeInteger(value) && context?.source && /^-?\d+$/.test(context.source)
        ? BigInt(context.source)
        : value);
  } catch {
    return text;
  }
}

const USAGE = `usage: hardfacts check OUTPUT [SOURCE ...] [--json] [--kinds ${[...KINDS].sort().join(",")}]\n`;

export function main(argv: string[]): number {
  let parsed;
  try {
    parsed = parseArgs({
      args: argv,
      allowPositionals: true,
      options: { json: { type: "boolean", default: false }, kinds: { type: "string" }, help: { type: "boolean", short: "h" } },
    });
  } catch {
    process.stderr.write(USAGE);
    return 2;
  }
  if (parsed.values.help) {
    process.stdout.write(USAGE);
    return 0;
  }
  const [command, ...paths] = parsed.positionals;
  if (command !== "check" || paths.length === 0) {
    process.stderr.write(USAGE);
    return 2;
  }
  const json = parsed.values.json;
  const kinds = parsed.values.kinds?.split(",").map((k) => k.trim()).filter(Boolean);
  if (kinds !== undefined && kinds.length === 0) { // an empty list would check nothing and pass
    process.stderr.write("hardfacts: --kinds needs at least one Kind\n");
    return 2;
  }
  let report;
  try {
    report = check(read(paths[0]), paths.slice(1).map(loadSource), kinds ? { kinds } : {});
  } catch (e) {
    process.stderr.write(`hardfacts: ${(e as Error).message}\n`);
    return 2;
  }
  if (json) {
    process.stdout.write(JSON.stringify(toJSON(report), null, 2) + "\n");
  } else {
    for (const c of report.unsupported) {
      const derived = c.derivation ? ` = ${c.derivation.expression}` : "";
      process.stdout.write(`UNSUPPORTED ${c.kind.padEnd(10)} ${JSON.stringify(c.text)} at ${c.span[0]}-${c.span[1]}${derived}\n`);
    }
    process.stdout.write(`${report.claims.length - report.unsupported.length}/${report.claims.length} hard facts supported\n`);
  }
  return report.ok ? 0 : 1;
}

process.exitCode = main(process.argv.slice(2));
