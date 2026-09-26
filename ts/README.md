# hardfacts (TypeScript)

Deterministic provenance for the numbers, dates, money and IDs your LLM writes. It pulls every hard fact (numbers, money, percentages, dates, times, phone numbers, emails, URLs, order and tracking IDs, and names with digits such as `COVID-19`) out of a model's output and checks each one against the sources the model was given. There are no model calls and no runtime dependencies, and a check takes about 0.2 ms. It reads English, Bahasa Melayu and 中文.

This is the TypeScript port of the Python reference implementation. The two agree exactly: on a shared conformance fixture, on 17,790 RAGTruth responses, on fuzzed text, and on real support-agent turns with their JSON tool results.

```ts
import { check, feedback } from "hardfacts";

const order = { order_id: "ORD-2024-0012", tracking: "EN123456789MY", eta: "2026-10-03", shipping_fee: 12.9 };
const report = check("Tracking EN123456780MY, arriving 2 October, RM 12.90 shipping.", [order]);

report.ok;           // false
report.unsupported;  // EN123456780MY (one digit off) and 2 October (the record says 3 October)
report.unexplained;  // unsupported values that aren't arithmetic on the reply's own values
if (!report.ok) messages.push({ role: "user", content: feedback(report) }); // verify and retry
```

An unsupported amount that the reply's own values produce carries its working, e.g. `$6.32` has `derivation.expression === "$101.12 − $94.80"`. It is still unsupported: the reviewer checks the operands.

Not on npm yet: packages come when the repository reaches 100 stars. Until then, build from a clone:

```bash
git clone https://github.com/seekerPrice/hardfacts && cd hardfacts/ts && npm install && npm run build
node dist/cli.js check reply.txt order.json   # exit 0 all supported · 1 unsupported · 2 usage error
```

Node ≥ 22. `dist/hardfacts.browser.js` is a single-file browser build that sets `globalThis.hardfacts`.

Benchmarks, design decisions and limits: see the repository's main README.

MIT.
