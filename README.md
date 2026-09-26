# hardfacts

**Your LLM just invented a tracking number. hardfacts catches it: deterministically, in about a millisecond, with no model calls.**

hardfacts pulls every *hard fact* out of an LLM's output (numbers, money, percentages, dates, times, phone numbers, emails, URLs, order and tracking IDs) and checks each one against the sources the model was given. It reports the values no source contains, and for every value that is supported it points at the evidence. Python and TypeScript, zero runtime dependencies, English + Bahasa Melayu + 中文.

```python
from hardfacts import check

order = {"order_id": "ORD-2024-0012", "carrier": "Pos Laju", "tracking": "EN123456789MY",
         "eta": "2026-10-03", "shipping_fee": 12.90}
draft = ("Your order ORD-2024-0012 ships via Pos Laju. "
         "Tracking: EN123456780MY, arriving 2 October, RM 12.90 shipping.")

for claim in check(draft, [order]).claims:
    print("✓" if claim.supported else "✗", claim.kind, claim.text)
```
```
✓ identifier ORD-2024-0012
✗ identifier EN123456780MY      ← one digit off: a parcel that doesn't exist
✗ date       2 October          ← the record says 3 October
✓ money      RM 12.90           ← matched by value against "shipping_fee": 12.9
```

When a flagged value is arithmetic on values the reply itself states, the flag shows the working, so a reviewer checks the operands instead of redoing the search:

```
✗ money      $6.32  = $101.12 − $94.80     ← still flagged: no source states it
```

## Results

Measured on [RAGTruth](https://github.com/ParticleMedia/RAGTruth) (17,790 responses from six LLMs with human-labelled hallucination spans, MIT). Every rule was developed on the train split. The **test split is scored once per release**: v0.1 at `78413c9`, and v0.2 at the frozen checker `96eaa4b` ([protocol](docs/adr/0004-benchmark-protocol.md), [raw results](bench/results/)).

| RAGTruth test | flags raised | span precision | hard-fact recall | response precision |
|---|---:|---:|---:|---:|
| naive baseline (every digit string must appear in the source) | 1,548 | 0.221 | 0.703 | 0.521 |
| hardfacts v0.1 | 289 | 0.737 | 0.578 | 0.833 |
| **hardfacts v0.2** | **281** | **0.758** | 0.578 | **0.850** |

- **Span precision** is the share of flags that overlap a span the annotators labelled as hallucinated. **Hard-fact recall** is the share of labelled spans containing a number (after removing list markers and "passage N" citations) that hardfacts flags.
- **Human labels undercount.** In v0.1, *all 76* test flags that miss a labelled span were audited twice, by two LLM auditors (separate Claude agents, each blind to the other, told to search the source for the value in any form). **29 are values the source never states** (a jury "of 12" the article never mentions, a restaurant "open since 1988"), 31 are values *derived* from the source (°F→°C, "based on 3 reviews"), and 16 are checker errors. Adding the inventions to the labelled hits, **83.7% of all flags point at a hallucination; counting derived values too, 94.5% point at a value the source doesn't contain.** The auditors agreed on 98.7% of correct-vs-error calls (Cohen's κ 0.96). Every verdict has a quoted piece of evidence, so any of them can be checked by hand in [the audit files](bench/audit/test/). v0.2 raises no flag outside a labelled span that v0.1 didn't already raise, so the same verdicts carry over. **86.1% of v0.2's flags point at a hallucination, and 97.2% counting derived values** ([delta audit](bench/audit/test-delta-8270819/)).
- **Controlled fault injection.** On the 1,732 test responses the annotators judged clean, hardfacts v0.2 **catches 96.4% of planted fabrications** (one digit of a real value changed: 1,032 plants across dates, times, money, percentages, phones and numbers). It **raises a flag on 1.6% of clean responses; the naive check flags 19.9%**. That is 12× fewer false alarms. v0.1 scored 96.2% and 1.8%. [Method](bench/fault_injection.py) · [v0.2 result](bench/results/fault-test-507877a.json).
- **Speed.** 0.19 ms per response in TypeScript and about 2 ms in Python (v0.2 is ~28% slower than v0.1, which measured 0.9 ms on an idle machine; `bench/speed.py` compares versions in one sitting), on RAGTruth prompts (2.6 KB on average) on one laptop core. An LLM judge takes seconds and costs about $0.002 a call ([worked cost model](examples/prefilter_router.py)).

The naive baseline's higher recall comes from flagging almost every number: it raises 5.4× as many flags, and more than three in four of them touch no labelled hallucination.

### A second dataset it was never tuned on: FaithBench

[FaithBench](https://github.com/vectara/FaithBench) (Vectara, NAACL 2025; CC BY-NC-SA, downloaded for evaluation only) has 750 news summaries by 10 modern LLMs, chosen *because* existing detectors disagreed on them. It was scored once, with no tuning, at `e93d226`, and the result was weaker. It is reported here as scored:

| FaithBench | flags | span precision (vs any annotation) | planted fabrications caught | clean summaries flagged |
|---|---:|---:|---:|---:|
| naive baseline | 210 | 0.295 | 100% | 10.9% |
| hardfacts, as scored (`e93d226`) | 153 | 0.444 | 95.6% | **12.0%** |
| hardfacts after the fix below (`f6b84f4`, no longer out-of-sample) | 89 | 0.652 | 95.6% | 5.1% |

Recall on planted fabrications generalised. Precision didn't, at first. Auditing all 85 unmatched flags found 64 checker errors, nearly all one bug: FaithBench sources are word-tokenised (`July 22 , 1947`, with a space before the comma), so the year didn't attach and correct dates were flagged. The fix is general and checked against RAGTruth train, where nothing moved. Because it was found on FaithBench, the post-fix row is a bug-fix measurement, not a second out-of-sample result. The audit also found 4 inventions the annotators missed, including rugby scores the source never states. FaithBench's labelled hallucinations are mostly prose-level, so hard-fact recall there is low (0.21), which is the expected ceiling for a value-level check. [Results](bench/results/) · [audit](bench/audit/faithbench/)

### A third dataset, from the use case it's built for: support agents (τ-bench)

[τ-bench](https://github.com/sierra-research/tau-bench) (Sierra, MIT) publishes real runs of GPT-4o and Claude 3.5 Sonnet as retail and airline support agents: 22,179 replies, each checked against the tool definitions, policy, user turns and JSON tool results the agent had seen. There are no hallucination labels, so two blind auditors classified samples of the flags. The run was pre-registered and recorded before any flag was read. [Full record](docs/reviews/2026-09-26-taubench.md).

| τ-bench | flags | replies flagged | planted fabrications caught |
|---|---:|---:|---:|
| naive baseline (same Sources as the last row) | 6,818 | 18.5% | 100% (by construction) |
| hardfacts, as scored (`bd9d22f`, harness corrected) | 4,322 | 11.6% | 93.1% |
| hardfacts after the fixes the audit led to (`49e677b`, not out-of-sample) | 3,411 | 8.75% | **98.9%** |

- **On support text, most flags are arithmetic.** Of the flags from the fixed checker, 90% are values the agent computed (fare totals, price differences), 5% are invented, and 5% were checker errors, since fixed. The auditors agreed on all 240 verdicts across both audits. They are the same model family, so read that as consistency.
- **The inventions are the failures this tool exists for:** "the gift card ending in **2692**" when the card is `gift_card_7250692`, a guessed user ID passed to a tool, a flight duration no tool returned.
- **The arithmetic goes wrong too.** 11 of 115 audited derived values were wrong: a fare difference taken against one leg of a two-leg trip, "12 options available" when 10 are, a $35.94 refund stated as $235.94. That's why each flag carries its Derivation. 45% of flags get one, and all 38 audited ones were real derivations. Only 0.5% of caught fabrications get one by coincidence.
- **What it doesn't show:** flags don't predict task failure (48% of both successful and failed runs have one). τ-bench tasks mostly fail on wrong actions, which a value checker can't see.

### The held-out test of all that: τ²-bench, where a prediction failed

Every rule since the first τ-bench run came from reading τ-bench flags, so τ-bench can't say whether they generalise. [τ²-bench](https://github.com/sierra-research/tau2-bench) (Sierra, MIT) publishes 4,448 runs of newer agents: Claude 3.7 Sonnet, GPT-4.1, GPT-4.1-mini and o4-mini. They cover airline, retail and a new telecom domain. The checker, metrics and fail thresholds were [pre-registered](docs/reviews/2026-09-26-tau2bench-preregistration.md) and frozen before the first score. [Results](docs/reviews/2026-09-26-tau2bench-results.md).

| prediction | predicted | τ²-bench | |
|---|---:|---:|---|
| planted fabrications caught | ≥ 97% | **98.2%** | pass |
| flags that are checker errors | ≤ 10% | **19.7%** (telecom 39.4%) | **fail** |
| flags carrying a Derivation | ≥ 30% | 37.8% | pass |
| fabrications "explained" by coincidence | ≤ 1% | 0.99% | pass, at the limit |
| replies flagged vs naive | under half | 6.6% vs 9.8% | miss |

The recall generalised and the precision didn't. Telecom agents write things τ-bench agents never did, such as "5G/4G/3G/2G" and "your line ending in 2002", and 24 of the 31 audited errors came from four such formats. They are fixed test-first in both ports, and 25 of the 31 now clear, with every audited invention still flagged. That is a post-fix measurement, not a held-out one. The audit also found a **circular Derivation**: an invented $1,707 total "explained" as the sum of its parts, one of which the agent had computed *from* the invented total. That is why a Derivation never changes a verdict.

## What it checks

| Kind | Read as the same Value | Example it catches |
|---|---|---|
| quantity | `1,200` · `1.2k` · `one thousand two hundred` · `二十一` · `dua ratus` | "injured 5 people" when the source says "six people" |
| money | `$2.1 billion` · `$2,100,000,000` · `RM1.2 juta` · `1200元` | an invented refund amount, or the wrong currency |
| percent | `15%` · `15 percent` · `15 peratus` · `百分之十五` | "60% chance of rain" against "63 percentage chance" |
| date | `2022-01-16` · `January 16, 2022` · `16 Jan 2022` · `2022年1月16日` | "February 7, **2022**" when the source only says "February 7" |
| time | `21:0` · `9 PM` · `9:00 p.m.` | "closes at 10 PM" against hours of `16:30-21:0` |
| temperature | `400°F` · `400 degrees F` · `400F` | a °C value the model converted itself |
| phone | `(510) 889-8690` · `510-889-8690` · `+1 510 889 8690` | a support line that doesn't exist |
| email, url | case- and `www.`-insensitive; a domain is supported by a deeper link or an address at it | an invented download link |
| identifier | `ORD-2024-0012` · `ord20240012` · booking codes like `XEHM8B` · "card ending in 1784", `**** 4242` | an invented tracking number, order ID or SKU; "ending in 2692" when the card is `gift_card_7250692` |

Partial values follow one rule: a claim may be *less* specific than its evidence, never more. So `February 7` is supported by `7 Feb 1945`, but `February 7, 2022` is not.

## What it doesn't check (read this before you rely on it)

- **Binding errors.** If the source says Gordon's net worth is $2.1 billion and the output gives Andrew $2.1 billion, the value has provenance, so hardfacts says it is supported. On the swap test (a whole source number moved to the wrong place) it catches 21.6%, almost all through Kind mismatches (a swapped time or date). For plain numbers the figure is 10%. An earlier version of this README said 42%. A benchmark bug counted fragment swaps as binding errors, and the deep-check audit found it ([review](docs/reviews/2026-09-26-deep-check.md)). The design choice is measured in [ADR-0006](docs/adr/0006-values-not-context.md).
- **Derived values.** A correct unit conversion, sum or count is still flagged, because no source states it ([ADR-0005](docs/adr/0005-derived-values-are-unsupported.md)). When the reply's own values produce it (`$6.32 = $101.12 − $94.80`), the flag carries that Derivation ([ADR-0007](docs/adr/0007-derivations-come-from-the-output.md)). It never marks the value correct: on τ-bench, 11 of 115 audited derivations used the wrong operands or count.
- **Prose.** "The hotel has a pool" is not a hard fact. Use hardfacts *in front of* an LLM judge, not instead of one.
- **Coincidence.** A small number in the output can be "supported" by the same number used for something else in the source. Value-level provenance can't tell them apart.

- **Signs and a few formats.** `-5°C` and `5°C` share a Value, because a leading `-` is as often a dash as a minus. Dates written in Chinese numerals (`二〇二五年十月三日`) and Indian lakh grouping (`₹1,50,000`) aren't read. Short voucher codes like `SAVE20` count as names, not IDs: that rule is measured (it keeps `COVID-19` and `B12` from flooding the flags), but it means an invented voucher code passes.

Known misses from the v0.1 test audit: ordinal date ranges (`October 20th and 21st, 2023`) and hyphenated number words (`two-kilometer`) have since been fixed. Units glued to numbers (`30minutes`) still aren't read. A later adversarial audit ([deep-check](docs/reviews/2026-09-26-deep-check.md)) found and fixed 60+ more edge cases in both languages: ISO timestamps, non-breaking spaces, Rupiah dot-thousands, unformatted phone numbers, all-digit tracking numbers, `9.30am` and others. A hostile review of those fixes then found 16 regressions in them, all fixed test-first. Among them were `$0.125` read as 125, US phones written with dots, and "2 malam" (two nights) read as 8 PM. The benchmark gate had stayed green through every one.

## Install and use

**Not on PyPI or npm yet.** Packages will be published when this repository reaches **100 stars**. Star it if you want `pip install hardfacts`. Until then, install from GitHub:

```bash
pip install "git+https://github.com/seekerPrice/hardfacts"     # Python ≥3.10, no dependencies
```

For TypeScript (Node ≥22, no dependencies), clone the repository and build `ts/` (`npm install && npm run build`).

```python
from hardfacts import check, feedback

report = check(output, [retrieved_passage, tool_result_dict])  # strings or JSON-like values
report.ok                 # True when every hard fact is supported
report.unsupported        # Claims with .kind .text .span .value, and .derivation when it's arithmetic
report.unexplained        # unsupported and not arithmetic on the reply's own values: the retry
                          # condition for a bot that must calculate totals or price differences
report.claims[0].evidence # where a supported value came from: source index + span (the first 10)
report.to_dict()          # JSON, including the rendered sources the spans index into

check(output, sources, kinds={"identifier", "money", "phone"})  # strict where it matters
feedback(report)          # a correction instruction for a verify-and-retry loop
```

```ts
import { check, feedback } from "hardfacts";

const report = check(output, [order], { kinds: ["identifier", "date", "money"] });
if (!report.ok) messages.push({ role: "user", content: feedback(report) });
```

```bash
hardfacts check reply.txt order.json kb.txt          # exit 0 all supported · 1 unsupported · 2 usage error
hardfacts check --json --kinds identifier,phone - order.json < reply.txt
hardfacts report transcripts.jsonl --html audit.html --fail-over 0.05   # a whole dataset (Python CLI)
```

`hardfacts report` reads one `{"id", "output", "sources"}` object per line and writes a self-contained audit: the share of responses with an unsupported hard fact, a breakdown by Kind, and the worst examples in context. Samples: [support-agent replies from τ-bench](examples/sample-report/support-agents.html) (4.5% of 4,937 GPT-4o replies state a value no source contains, and half of those values are shown as arithmetic with their working) and [900 RAGTruth business write-ups](examples/sample-report/business-listings.html) (11.2%, mostly opening hours).

Integration examples, all runnable offline:
- [Python verify-and-retry](examples/verify_and_retry.py)
- [Pydantic AI `output_validator` that raises `ModelRetry`](examples/pydantic_ai_output_validator.py)
- [Vercel AI SDK v7 verify-and-retry](ts/examples/ai-sdk-verify-and-retry.ts)
- [Free pre-filter → sampled LLM judge, with cost maths](examples/prefilter_router.py)
- [MCP server](integrations/mcp/): `check_hard_facts` as a tool any agent (Claude Code, Claude Desktop, Cursor) can call on its own draft

## How it works

1. **Extract.** Recognisers run in priority order over each text (URL, email, date, phone, money, percent, temperature, time, identifier, then numbers and number words). Each one claims the characters it matches, so `21:0` is a time and never the quantities 21 and 0. Things that look like facts but aren't are claimed as *exempt*: list markers, "a summary in 88 words", "steps 6 and 7", "out of 5 stars", "seven days a week", names like `COVID-19`.
2. **Normalise.** Each fact becomes a typed Value: an exact decimal, a currency plus amount, an EDTF-style partial date (`XXXX-02-07`), or the set of 24-hour readings a time allows. A text that writes any 13:00–23:59 time is on the 24-hour clock, so its bare `9:00` means 09:00.
3. **Match.** Each claim in the output is compared with every fact in the sources using that Kind's rule: exact decimals, compatible currencies, specificity for dates, overlapping readings for times, suffix rules for phones and last-digit references. When a match is doubtful the claim counts as supported ([ADR-0003](docs/adr/0003-precision-over-recall.md)). A pre-filter that cries wolf gets switched off.
4. **Explain.** Each unsupported number, amount or percentage is searched for as a difference, a sum of 2–5, or a multiple of the reply's own supported values of that Kind. The search never draws on the sources, because there it would "explain" most fabrications ([ADR-0007](docs/adr/0007-derivations-come-from-the-output.md)).

The Python package is the reference. The TypeScript port reproduces it: every shared conformance case passes, and Claims, Values, verdicts and spans are identical on all 17,790 RAGTruth responses ([differential test](bench/differential.py)). On fuzzed texts dense in digits, currencies, CJK numerals, Malay number words, emoji and odd line breaks, the rendered Sources and Evidence are identical as well ([fuzz differential](bench/fuzz_differential.py)). Spans are offsets in each language's own string units: code points in Python, UTF-16 units in JavaScript, so `text.slice(...span)` works natively in each. The differential tests convert before comparing. So is a sample of real support-agent turns with their JSON tool results ([τ-bench differential](bench/taubench_differential.py)). The few inherent differences, such as span units and the runtimes' Unicode versions, are listed in [docs/port-parity.md](docs/port-parity.md).

## Reproduce

`tools/verify.sh` runs every gate below in one go (tests in both languages, the release check, the train gate and all three differentials) and exits non-zero on any failure.

```bash
uv sync && uv run pytest                          # Python tests, including property-based invariants
cd ts && npm install && npm test && cd ..         # TypeScript tests, including the shared conformance fixture
bench/fetch_ragtruth.sh
uv run python bench/ragtruth.py --split train     # development numbers (tune here only)
uv run python bench/fault_injection.py --split train
uv run python bench/audit.py summarize --split test
bench/fetch_taubench.sh
uv run python bench/taubench.py                   # support agents: flags, fault injection, Derivations
uv run python bench/taubench_audit.py summarize --name taubench-postfix
uv run python bench/taubench_differential.py      # TypeScript = Python on real agent turns
```

## Design record

Decisions and the numbers behind them live in [`docs/adr/`](docs/adr/): why the core is deterministic ([0002](docs/adr/0002-deterministic-zero-dependency-core.md)), why doubt resolves to supported ([0003](docs/adr/0003-precision-over-recall.md)), the train/test protocol ([0004](docs/adr/0004-benchmark-protocol.md)), why conversions are flagged ([0005](docs/adr/0005-derived-values-are-unsupported.md)), three matching strategies that were measured and rejected ([0006](docs/adr/0006-values-not-context.md)), and why Derivations draw only on the reply's own values ([0007](docs/adr/0007-derivations-come-from-the-output.md)). The build log is in [`docs/worklog.md`](docs/worklog.md). The long-form write-up is [`docs/writeup.md`](docs/writeup.md).

## License and credits

MIT. RAGTruth (ParticleMedia) and τ-bench (Sierra) are MIT-licensed and are downloaded, not redistributed. FaithBench (Vectara) is CC BY-NC-SA and is downloaded for evaluation only.

hardfacts was designed, built, benchmarked and audited with [Claude Code](https://claude.com/claude-code) (Claude Opus 5.5) in one autonomous session, for Loo Tan Yu Heng (Lucas), who maintains it. The trail is in [`CHANGELOG.md`](CHANGELOG.md), [`docs/reviews/`](docs/reviews/) and the ADRs.
