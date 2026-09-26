# Changelog

The repository is public on GitHub. Nothing is on PyPI or npm yet (see ROADMAP.md). The versions below are milestones in the repository.

## Unreleased

- **Percentages computed from the reply's own values show their working** ([ADR-0007](docs/adr/0007-derivations-come-from-the-output.md), amended): "a return of 37.9%" carries `(137.90 − 100.00) ÷ 100.00 × 100`, for a percentage stated to a decimal, using only the three values written nearest it. The first build used every number in the reply, and a hostile review (round 15) showed chance matches then grow with the reply (42% of random percentages at 20 numbers). Bounded, table QA goes from 61.9% to 61.4% of correct answers flagged, and τ²-bench coincidences stay at 1.0%.
- **Hostile reviews, rounds 8–10:**
  - round 8, of the citation rule: 1 high (an answer written as a bracketed list, "the scores were [7, 8, 9]", went unchecked)
  - round 9, of names: 1 high (quadratic time on 20,000 names) and 3 low (hyphens merging digit runs, full-width digits)
  - round 10, of the Malaysian-text fixes: 1 high (an invented `十块五毛五` passed as 10.5) and 2 lower (fractions after "on", a counter read as money)
- **Round 11, a whole-library adversarial review** (not a diff review), fixed test-first in both ports:
  - **A bare JSON amount is in the currency its Source names.** `{"amount": 50, "currency": "MYR"}` no longer supports "USD 50", "€50" or "$50". A Source naming no currency, or a compatible one, still does.
  - Chinese shorthand: `一万五` is 15,000 and `一百五` is 150. They were read as 10,005 and 105.
  - European amounts (`1.500,00 €`), `lakh` and `crore`, and minor units on their own (`50 sen` = RM0.50, `50¢`, `77-cent`).
  - A year-less date also reads with the nearest year. On 2025-12-30, "Jan 2" reads as 2026 as well as 2025.
  - **Round 12, a review of those fixes:**
    - The currency rule first read any code anywhere in a Source (`"note": "USD accepted"` flagged a correct "RM 50"). It now reads only currency-named keys.
    - It had also made a 60 KB answer take 277 s. A blocked Source is now skipped in one step.
    - Nearest-year had replaced the anchor year and could make 29 February 2025. It now adds a reading and never makes an invalid date.
  - **Round 13, a review of round 12:**
    - Money Evidence names its own currency, so "RM12" in a Source whose currency key says USD still supports "RM12".
    - A JSON Source passed as a string, as tool messages usually are, now names its currency. It had switched the check off.
    - Currency keys are matched by word, so `ccy_code` counts and "recurring" doesn't.
    - The half-year window counts days, and "Feb 29" reads as the nearest leap year.
    - The TypeScript walk no longer overflows the stack on a large array.
  - **Round 14, a review of round 13:** a deeply nested JSON-looking string crashed Python's parser (`RecursionError` at 1,000 levels on Python 3.10). Nesting deeper than 200 is no longer parsed. An anchor date that doesn't exist ("Today is 31 April") no longer raises.
  - After these rounds, τ²-bench fabrications caught are 98.8%, up from 98.2%, with the same 4,859 flags (post-fix, not held-out).
  - Time zones, invented country codes, last-digit references matching phone numbers, and weekdays are recorded in ROADMAP.md.
- **Names with digits** (new Kind `name`, [ADR-0008](docs/adr/0008-names-are-checked-against-their-siblings.md)). `COVID-12` is flagged when a source says `COVID-19`, and `H2N1` when it says `H1N1`. A name is checked only against same-shaped names in the sources, so a name no source mentions still passes. On RAGBench, fabrications planted into names are caught 96% of the time, up from 46%, and 1 of 10,125 correct responses is newly flagged.
- **Middle-dot decimals** (`37·8°C`) are read as decimals.
- **Malaysian support text** (found by `bench/sea_probe.py`, 30 BM, 中文 and Manglish replies):
  - Colloquial `八块五` and `八元五角` are 8.50, and `十块五毛五` is 10.55. A digit that starts the next word is not read as tenths: `三块五花肉` is three pieces of pork belly.
  - "arrive 3/10" is a date with both readings (3 October in Malaysia, 10 March in the US) after a strong date word. After a weak one ("after 1/2 hour", "and 1/4 cup") it is still a fraction.
  - Amounts written out for text-to-speech are one amount: "seratus empat puluh sembilan ringgit sembilan puluh sen", "one hundred forty-nine dollars and ninety cents", "RM149 dan 90 sen".
  - The probe now has 0 false alarms and 0 missed errors, and 2 of ~40,000 RAGTruth and τ-bench outputs change. A latent Python bug that read "9/0" as a date was found by the port differential and fixed.
- **Citation markers** (`[10]`, `[1, 2, 5]`, `[1-6]`, `[^2]`, `[Doc 3]`) are no longer claims. They were 24 of the 30 checker errors a blind audit found on RAGBench. A marker counts only where it closes a clause, so a bracketed list stated as the answer ("the scores were [7, 8, 9]") is still checked. That regression was found by a hostile review of the first version.
- **RAGBench**, pre-registered ([results](docs/reviews/2026-09-27-ragbench-results.md)): 11,802 responses over 12 RAG datasets, compared with RAGAS, TruLens and a GPT-3.5 judge on the same responses. 4 of 6 predictions pass. **Table-arithmetic QA (FinQA, TAT-QA) fails**: 61.8% of correct answers are flagged, because ratios and percentage changes aren't Derivations. A stricter ratio search was measured and not built (`bench/ratio_experiment.py`).
- **Integrations:** an OpenAI Agents SDK output guardrail and a LangChain `create_agent` middleware (verify, retry once, hand off).

## 0.2.0 (unreleased)

Support-bot readiness, from testing on real support agents (τ-bench), a held-out τ²-bench run, and rounds of adversarial review.

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
- **Port parity.**
  - Python renders JSON Sources the JavaScript way: integer-like keys first, whole floats without `.0`.
  - The conformance fixture is compared strictly and includes `feedback()` text.
  - A τ-bench differential runs in CI.
- **Performance.** Two V8 regex slow paths are gone: TypeScript takes about 0.2 ms per RAGTruth response.
- **Packaging.** The sdist is an allowlist, and it shrank from 7.8 MB, which included `node_modules`, to 61 KB. `py.typed` is included, CI checks the built release, and the npm package has a README.
- **Breaking** (for anyone on a local 0.1 build):
  - `Report.to_dict()` claims gain a `derivation` key.
  - `Report.sources` renders JSON in JavaScript key order.
  - Identifier Values of last-digit references start with `*`.
  - A Claim lists at most 10 pieces of Evidence, the first in Source order (`EVIDENCE_PER_CLAIM`).

## 0.1.0 (unreleased; RAGTruth test split scored once at `78413c9`)

The first complete version: ten kinds of hard fact in English, Bahasa Melayu and 中文; the Python reference and a TypeScript port; the RAGTruth benchmark with a train/test protocol, fault injection and blind audits; the FaithBench out-of-sample run; the CLI, `hardfacts report`, the MCP server and the integration examples.
