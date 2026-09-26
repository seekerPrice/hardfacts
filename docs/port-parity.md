# Where the Python and TypeScript ports can differ

The Python package is the reference implementation, and the TypeScript port is held to it in four ways:

- **Shared conformance fixture.** It is recorded from every `check()` call in the Python tests (`ts/test/fixture.json`).
- **RAGTruth differential.** It covers all 17,790 responses and compares Claims, Values, verdicts and spans.
- **Fuzz differential.** It generates texts dense in the things hardfacts reads, and also compares the rendered Sources, every piece of Evidence and every Derivation.
- **τ-bench differential.** Real support-agent turns with their JSON tool results, compared on everything (`bench/taubench_differential.py`).

All four are identical, and the conformance fixture is compared strictly, JSON Sources included. A hostile parity review (26 September 2026) still found places where the two ports can disagree. Some were fixed; the rest are inherent, and are listed here.

## Fixed

- **The phone cue window.** It counted UTF-16 units in TS but code points in Python, so an emoji between "call" and a number changed the verdict. Both now count characters.
- **Number words above 2^53.** TS summed these in floating point, so "one hundred hundred trillion and one" rounded. TS now uses BigInt.
- **Non-ASCII digits after a long number.** Python's decimal-point test treated `৫` in `1234567890.৫` as a digit and TS didn't. Both now use ASCII `[0-9]`.
- **A lone low surrogate before a number word.** It made TS test the wrong character.
- **Integral floats in a JSON Source.** Python rendered `1518.0` and TS `1518`, because `JSON.parse` has no `1518.0`. Python now renders whole floats the way JavaScript does (`-0.0` is `0`). The τ-bench differential found this on 197 of 3,000 real turns.
- **Object key order.** JavaScript moves integer-like keys (array indices up to 2³² − 2) to the front in numeric order, and `JSON.parse` keeps no other order. Python now renders keys in that order. Tool results key records by numeric ID often enough that this differed on 22% of sampled τ-bench turns: a fuzz blind spot, and a gap earlier documented here as "inherent".
- **Deeply nested Sources.** In both ports they overflowed the recursive renderer. Rendering is now iterative.
- **Lone surrogates under `--json`.** They crashed the Python CLI. They are now written as `\uXXXX` escapes, as JavaScript writes them.

## Inherent, and why

| Difference | Python | TypeScript | Effect on verdicts |
|---|---|---|---|
| Span units | code points | UTF-16 units | none: each slices its own strings (`text[a:b]`, `text.slice(a, b)`) |
| Values over 1,000 significant digits | rounded by the 1,000-digit Decimal context | exact (BigInt) | only on inputs no model writes |
| Integers over 4,300 digits in a Source | `ValueError` (CPython's int-to-string safety limit); the CLI treats such a file as text | parsed exactly | Python refuses the Source |
| `NaN` / `Infinity` in a `.json` file | parsed as numbers | not JSON, so read as raw text | the rendered text differs |
| Lone surrogates inside structured Sources | kept as one character | escaped to six (`\udc00`) | the rendered text and spans differ |
| Unicode tables | the runtime's (Python 3.14: Unicode 16.0) | the runtime's (Node 24: Unicode 17.0) | letters added in Unicode 17 count as letters only in Node |
| CLI `--kinds` whitespace | `str.strip()` | `String.prototype.trim()` | exotic whitespace (`\x1c`–`\x1f`, `\x85`, BOM) is accepted by one CLI only |
| CLI argument order | argparse: options after the subcommand | options anywhere | `--json check …` is a usage error in Python only |
| CLI text output | `repr()` quoting | `JSON.stringify` quoting | cosmetic. `--json` output is byte-identical |

For a Python caller, the one visible effect of rendering the JavaScript way is in `report.sources`. `{"b": 1, "7": 2}` is searched as `{"7": 2, "b": 1}`, and `2.0` as `2`. Values and verdicts are unchanged.

If one of the remaining differences matters for your use, parse the JSON once in your own code and pass the same strings to either port. Two text Sources render identically in both.
