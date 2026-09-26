// Concatenate the built modules into one script that sets globalThis.hardfacts.
// No bundler needed: the modules only import each other, one line per import.
//   npm run build && node scripts/bundle-browser.mjs > dist/hardfacts.browser.js
import { readFileSync } from "node:fs";

const order = ["regex", "decimal", "extract", "index"];
const body = order
  .map((name) => readFileSync(new URL(`../dist/${name}.js`, import.meta.url), "utf8"))
  .map((src) => src.replace(/^import .*$/gm, "").replace(/^export /gm, "").replace(/^\/\/# sourceMappingURL.*$/gm, ""))
  .join("\n");

// Modules share one scope here, and a repeated top-level function silently replaces the first
// (a clash between two `LETTER` constants once broke the demo), so refuse to bundle a clash.
const names = [...body.matchAll(/^(?:async )?(?:function\*?|const|let|class) ([A-Za-z_$][\w$]*)/gm)].map((m) => m[1]);
const clashes = [...new Set(names.filter((n, i) => names.indexOf(n) !== i))];
if (clashes.length) {
  console.error(`bundle-browser: top-level names defined in more than one module: ${clashes.join(", ")}`);
  process.exit(1);
}
process.stdout.write(`(() => {\n${body}\nglobalThis.hardfacts = { check, feedback, toJSON, KINDS, KIND_NAMES };\n})();\n`);
