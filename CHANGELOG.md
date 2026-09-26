# Changelog

Nothing has been published yet. The versions below are milestones in the repository.

## Unreleased

- **Citation markers** (`[10]`, `[1, 2, 5]`, `[1-6]`, `[^2]`, `[Doc 3]`) are no longer claims. They were 24 of the 30 checker errors a blind audit found on RAGBench.
- **RAGBench**, pre-registered ([results](docs/reviews/2026-09-27-ragbench-results.md)): 11,802 responses over 12 RAG datasets, compared with RAGAS, TruLens and a GPT-3.5 judge on the same responses. 4 of 6 predictions pass. **Table-arithmetic QA (FinQA, TAT-QA) fails**: 61.8% of correct answers are flagged, because ratios and percentage changes aren't Derivations. A stricter ratio search was measured and not built (`bench/ratio_experiment.py`).
- **Integrations:** an OpenAI Agents SDK output guardrail and a LangChain `create_agent` middleware (verify, retry once, hand off).

## 0.2.0 (unreleased)

Support-bot readiness, from testing on real support agents (τ-bench) and three adversarial reviews.

- **Derivations** ([ADR-0007](docs/adr/0007-derivations-come-from-the-output.md)). An unsupported number, amount or percentage now carries the arithmetic that produces it from the reply's own supported values (`$6.32 = $101.12 − $94.80`), with its operand spans. The verdict never changes.
  - `Report.unexplained` lists what neither a source nor such arithmetic accounts for.
  - `feedback()` shows the working instead of asking the model to drop the value.
  - The MCP tool returns `computed_as` and `ok_except_calculations`.
  - `hardfacts report` separates arithmetic from unexplained values.
- **Tool-result patterns.**
  - Float noise (`3.759999999999991` is 3.76).
  - Numbers inside snake_case IDs (`credit_card_7574394`).
  - Year-less dates the user typed.
  - Six-character booking codes (`XEHM8B`).
  - Last-digit references ("card ending in 1784", `**** 4242`). These are supported only by a number that *ends* in those digits.
  - Ordinal day ranges ("May 19th and 20th", "20 and 21 October").
- **Markdown and dev-tool output.** Trailing `*` and backticks are no longer part of a URL. Digits in a URL path are stated numbers (`…/pull/3337` supports "PR #3337"), and short and long git hashes name one commit.
- **A Claude Code Stop hook** (`integrations/claude-code/`). It checks each of Claude's answers against the tool results and notices the session showed it. It is opt-in, with a warn mode.
- **Hostile reviews of the fixes themselves, in rounds,** all fixed test-first in both ports:
  - round 2: 16 regressions (5 high) and 15 port divergences
  - round 3: 13 regressions (6 high) and 4 high port findings
  - round 4: 14 findings (6 high)
  - round 5: 12 findings (6 high)
  - round 6: 12 findings (6 high, one of them a crash)
  - round 7, of the τ² fixes: 5 findings (2 high, e.g. "3/16 inch" in a Source vouching for "March 16")
- **Indexed matching.** Evidence is looked up by keys derived from the matching rules, and checked against brute force in CI. 50 KB of dates: 36 s → 0.34 s.
- **τ²-bench**, pre-registered as a held-out test of the τ-bench-era rules ([results](docs/reviews/2026-09-26-tau2bench-results.md)). It covers 4 newer agents and a new telecom domain.
  - 98.2% of planted fabrications were caught (prediction ≥ 97%: pass).
  - **The checker-error prediction failed.** 19.7% of flags were the checker's own mistakes, against a prediction of ≤ 10% (39.4% in telecom).
  - The causes are fixed, post-fix: slash-joined lists ("5G/4G/3G", "100Mbps/20Mbps"), URLs in curly quotes, "line ending in 2002", "ending in …1863", unambiguous month/day dates after a date word ("on 5/19"), and "May 27 and 28, 2024". 25 of the 31 audited errors now clear, and every audited invention is still flagged.

  `tools/verify.sh` runs every gate.
- **Round-2 regressions fixed.** The hostile review of the deep-check fixes found 16, including `$0.125` read as 125, dotted US phones, a count stealing a date, and "2 malam" read as 8 PM.
- **Port parity.**
  - Python renders JSON Sources the JavaScript way: integer-like keys first, whole floats without `.0`.
  - The conformance fixture is compared strictly and includes `feedback()` text.
  - A τ-bench differential runs in CI.
- **Performance.** Two V8 regex slow paths are gone: TypeScript takes ~0.18 ms per RAGTruth response.
- **Packaging.** The sdist is an allowlist, and it shrank from 7.8 MB, which included `node_modules`, to 61 KB. `py.typed` is included, CI checks the built release, and the npm package has a README.
- **Breaking** (for anyone on a local 0.1 build):
  - `Report.to_dict()` claims gain a `derivation` key.
  - `Report.sources` renders JSON in JavaScript key order.
  - Identifier Values of last-digit references start with `*`.
  - A Claim lists at most 10 pieces of Evidence, the first in Source order (`EVIDENCE_PER_CLAIM`).

## 0.1.0 (unreleased; RAGTruth test split scored once at `78413c9`)

The first complete version: ten kinds of hard fact in English, Bahasa Melayu and 中文; the Python reference and a TypeScript port; the RAGTruth benchmark with a train/test protocol, fault injection and blind audits; the FaithBench out-of-sample run; the CLI, `hardfacts report`, the MCP server and the integration examples.
