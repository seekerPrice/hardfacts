# hardfacts

[![ci](https://github.com/seekerPrice/hardfacts/actions/workflows/ci.yml/badge.svg)](https://github.com/seekerPrice/hardfacts/actions/workflows/ci.yml) · **[Try it in your browser](https://seekerprice.github.io/hardfacts/)** · MIT · Python + TypeScript

**Your LLM just invented a tracking number. hardfacts catches it: deterministically, in milliseconds, with no model calls.**

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
- [OpenAI Agents SDK output guardrail](examples/openai_agents_guardrail.py): tools record their results in the run context, and the guardrail trips on an answer that states a value none of them contain (`--offline` runs without a key)
- [LangChain `create_agent` middleware](examples/langchain_middleware.py): checks each final answer, sends the feedback back to the model once, then hands off (runs offline with a fake model)
- [Vercel AI SDK v7 verify-and-retry](ts/examples/ai-sdk-verify-and-retry.ts)
- [Free pre-filter → sampled LLM judge, with cost maths](examples/prefilter_router.py)
- [MCP server](integrations/mcp/): `check_hard_facts` as a tool any agent (Claude Code, Claude Desktop, Cursor) can call on its own draft

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
| name | `COVID-19` · `covid19`, checked only against same-shaped names in the sources ([ADR-0008](docs/adr/0008-names-are-checked-against-their-siblings.md)) | "COVID-12" or "H2N1" when the source says COVID-19 or H1N1; "Schedule 16G" for 13G |

Partial values follow one rule: a claim may be *less* specific than its evidence, never more. So `February 7` is supported by `7 Feb 1945`, but `February 7, 2022` is not.

## What it doesn't check (read this before you rely on it)

- **Binding errors.** If the source says Gordon's net worth is $2.1 billion and the output gives Andrew $2.1 billion, the value has provenance, so hardfacts says it is supported. On the swap test (a whole source number moved to the wrong place) it catches 21.6%, almost all through Kind mismatches (a swapped time or date). For plain numbers the figure is 10%. An earlier version of this README said 42%. A benchmark bug counted fragment swaps as binding errors, and the deep-check audit found it ([review](docs/reviews/2026-09-26-deep-check.md)). The design choice is measured in [ADR-0006](docs/adr/0006-values-not-context.md).
- **Derived values.** A correct unit conversion, sum or count is still flagged, because no source states it ([ADR-0005](docs/adr/0005-derived-values-are-unsupported.md)). When the reply's own values produce it (`$6.32 = $101.12 − $94.80`), the flag carries that Derivation ([ADR-0007](docs/adr/0007-derivations-come-from-the-output.md)). It never marks the value correct: on τ-bench, 11 of 115 audited derivations used the wrong operands or count.
- **Prose.** "The hotel has a pool" is not a hard fact. Use hardfacts *in front of* an LLM judge, not instead of one.
- **Coincidence.** A small number in the output can be "supported" by the same number used for something else in the source. Value-level provenance can't tell them apart.

- **Signs and a few formats.** `-5°C` and `5°C` share a Value, because a leading `-` is as often a dash as a minus. Dates written in Chinese numerals (`二〇二五年十月三日`) and Indian lakh grouping (`₹1,50,000`) aren't read. Short voucher codes like `SAVE20` count as names, not IDs: that rule is measured (it keeps `COVID-19` and `B12` from flooding the flags), but it means an invented voucher code passes.

Known misses from the v0.1 test audit: ordinal date ranges (`October 20th and 21st, 2023`) and hyphenated number words (`two-kilometer`) have since been fixed. Units glued to numbers (`30minutes`) still aren't read. A later adversarial audit ([deep-check](docs/reviews/2026-09-26-deep-check.md)) found and fixed 60+ more edge cases in both languages: ISO timestamps, non-breaking spaces, Rupiah dot-thousands, unformatted phone numbers, all-digit tracking numbers, `9.30am` and others. A hostile review of those fixes then found 16 regressions in them, all fixed test-first. Among them were `$0.125` read as 125, US phones written with dots, and "2 malam" (two nights) read as 8 PM. The benchmark gate had stayed green through every one.

The known gaps, with their numbers, are in [ROADMAP.md](ROADMAP.md).

## Results at a glance

| benchmark | what was measured | hardfacts | naive "every number must appear" check |
|---|---|---:|---:|
| RAGTruth test split (17,790 human-labelled responses; test scored once per release) | share of flags on a labelled hallucination | **0.758** | 0.221 |
| same, after a blind audit of the flags the labels missed | share of flags that are real hallucinations | **86%** | n/a |
| RAGTruth, planted one-digit fabrications | caught / clean responses falsely flagged | **96.4% / 1.6%** | 100% / 19.9% |
| τ²-bench, 4 support agents, **pre-registered held-out run** | planted fabrications caught | **98.2%** | 100% |
| same | flags that were the checker's own mistakes | **19.7%**: predicted ≤ 10%, so this prediction failed | n/a |
| RAGBench, 10 RAG datasets (GPT-4 labels), **pre-registered** | share of flagged responses that are unfaithful, at the same flag count | **41.0%** (post-fix 50.2%) | RAGAS 39.0% · GPT-3.5 judge 27.1% · TruLens 14.8% |
| RAGBench, FinQA + TAT-QA (table arithmetic) | correct answers flagged | **61.8%**: predicted ≤ 40%, a failure | n/a |

The failed predictions and their causes are written up in [τ²-bench](docs/reviews/2026-09-26-tau2bench-results.md) and [RAGBench](docs/reviews/2026-09-27-ragbench-results.md). On RAGBench, RAGAS is still more precise on 6 of the 10 datasets taken one at a time, and hardfacts catches only about 1 in 10 unfaithful responses, because most are wrong in prose. The fixes are labelled post-fix, not out-of-sample. Full tables, including FaithBench and τ-bench, are in [docs/results.md](docs/results.md).

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

Decisions and the numbers behind them live in [`docs/adr/`](docs/adr/): why the core is deterministic ([0002](docs/adr/0002-deterministic-zero-dependency-core.md)), why doubt resolves to supported ([0003](docs/adr/0003-precision-over-recall.md)), the train/test protocol ([0004](docs/adr/0004-benchmark-protocol.md)), why conversions are flagged ([0005](docs/adr/0005-derived-values-are-unsupported.md)), three matching strategies that were measured and rejected ([0006](docs/adr/0006-values-not-context.md)), and why Derivations draw only on the reply's own values ([0007](docs/adr/0007-derivations-come-from-the-output.md)). The long-form write-up is [`docs/writeup.md`](docs/writeup.md).

## License and credits

MIT. RAGTruth (ParticleMedia) and τ-bench (Sierra) are MIT-licensed and are downloaded, not redistributed. FaithBench (Vectara) is CC BY-NC-SA and is downloaded for evaluation only.

hardfacts was designed, built, benchmarked and audited with [Claude Code](https://claude.com/claude-code) (Claude Opus 5.5) in one autonomous session, for Loo Tan Yu Heng (Lucas), who maintains it. The trail is in [`CHANGELOG.md`](CHANGELOG.md), [`docs/reviews/`](docs/reviews/) and the ADRs.
