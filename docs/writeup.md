# Your LLM invented a tracking number

*Building a deterministic check for the facts LLMs make up, and measuring it honestly.*

A drafting model in a customer-support pipeline once wrote a perfectly plausible shipping tracking number. The format was right and it sat naturally in a reply about the customer's order. It also did not exist. Anyone who followed it would be chasing a parcel through a courier's website that had never heard of it.

That failure has a shape worth naming. The model wasn't vague or wrong about the world. It supplied a **hard fact**, a value that feels checkable, and nothing it had been given contained that value. Tracking numbers, refund amounts, dates, opening hours, phone numbers, order IDs, percentages: these are exactly the tokens people act on, and the easiest for a fluent model to fabricate.

`hardfacts` is a small library that catches them. It extracts every hard fact from an output, normalises it, and checks it against the sources the model was given. It reports the values nothing supports, and gives evidence for the ones that are supported. This write-up covers how it got from 22% precision to 76%, the ideas the benchmark rejected, and how to measure a checker like this without fooling yourself.

## Why not ask an LLM to judge?

You can, and for prose ("the hotel has a pool") you should. For hard facts it's the wrong tool:

- **Cost and latency.** A small judge call over a 1k-token context costs about $0.002 and takes seconds. Every response pays it.
- **Non-determinism.** The same response can pass on Monday and fail on Tuesday, so a flag can't go in a bug report or a CI gate.
- **It's a lookup problem.** "Does 1Z999AA10123456785 appear in the order record?" doesn't need reasoning. It needs the right notion of *equal*.

So the goal was a deterministic, dependency-free check that costs a few milliseconds and runs on every response. The paid judge then goes where only a judge helps.

## The naive version, and why it fails

The obvious implementation is one line: every digit string in the output must appear in the source. On [RAGTruth](https://github.com/ParticleMedia/RAGTruth) (17,790 responses from six LLMs, with human-labelled hallucination spans) it has **22% span precision**. More than three in four flags touch nothing the annotators called a hallucination.

Reading a few hundred of those false positives shows they aren't random. They're structural:

| False positive | Why it isn't a fact about the world |
|---|---|
| `5. Rinse the glass…` | a list marker |
| `Here is a summary in 88 words:` | a statement about the output itself |
| `open until 9 PM` vs source `21:0` | same time, different clock |
| `a 4-star rating` vs `"stars": 4.0` | same number, different notation |
| `open seven days a week` | an idiom for "every day" |
| `a 73-year-old deputy` | parsed as an ID, not the quantity 73 |

Every row is fixable, and fixing them is the project.

## Typed facts, not digit strings

The core idea is that a hard fact has a **Kind** and a **Value**, and two facts are compared by Value under that Kind's rules:

- `21:0`, `9 PM` and `9:00 p.m.` share the Value 21:00. A bare `9:00` could be 09:00 or 21:00, *unless the text elsewhere writes 17:30*. Then it's on the 24-hour clock and means 09:00.
- `$2.1 billion` and `$2,100,000,000` are the same exact decimal, while `$2 billion` is not. There's no fuzzy tolerance.
- Dates are partial records. `February 7` is supported by `7 Feb 1945`, but `February 7, 2022` is *not*. A claim may be less specific than its evidence, never more, and that single rule catches false precision.
- `(510) 889-8690` and `+1 510 889 8690` are the same number. A claim can't invent an area code, though.
- `ORD-2024-0012` equals `ord20240012`, but `AB123` is not supported by `XAB1234`.

Recognisers run in priority order and *claim* the characters they match. `21:0` is a time and can never also be the quantities 21 and 0. Things that look like facts but aren't (list markers, "88 words", "steps 6 and 7", "out of 5 stars", `COVID-19`) are claimed as exempt, so nothing downstream re-reads them.

Here is every change as measured on the train split. The test split stayed untouched until the end.

| Change (train split) | span precision | hard-fact recall |
|---|---:|---:|
| naive digit match | 0.247 | 0.651 |
| exempt list markers and "N words" | 0.468 | 0.476 |
| times with 12/24-hour readings | 0.608 | 0.525 |
| money, percent, magnitudes | 0.600 | 0.524 |
| number words (small ones are evidence only) | 0.635 | 0.515 |
| dates with partial-date semantics | 0.661 | 0.504 |
| identifiers: names vs codes, number compounds | 0.681 | 0.505 |
| fixes from auditing 120 false positives | 0.710 | 0.501 |
| fixes from code review (24-hour clock context) | **0.718** | **0.544** |

Two of those rows taught the most.

**"Letters plus digits" is a terrible definition of an identifier.** The first cut flagged `4.5-star` 162 times, `COVID-19` 88 times and `73-year-old` dozens of times, and precision fell to 0.43. The working rule is that codes have at least four digits, or three digits and two letters, or a `#` tag. Shorter mixes are names. `N-word` compounds are a quantity followed by a description.

**Spelled-out small numbers are almost always derived.** "The two men", "three reviews", "seven days a week": `seven` alone caused 234 false positives. Numbers under ten written as words (which is what style guides prescribe) now count as evidence but never as claims.

## What the benchmark said no to

Precision here matters more than recall, and that's a deliberate trade. A pre-filter that cries wolf gets switched off within a week. So every loosening had to earn its place, and three that sounded obviously right didn't:

- **Accept unit conversions.** If the source says 400°F, isn't "(200°C)" fine? Treating rounded conversions as supported removed 77 QA false positives but lost 39 real catches. RAGTruth's annotators, like any strict reader, label an added conversion as baseless information. Conversions stay flagged.
- **Require unit agreement.** If `5 people` must match a `5` followed by `people`, coincidental support goes away. Recall on swapped numbers went from 19% to 30%, but precision fell from 0.72 to 0.60 and false alarms more than doubled. Sources say `6 victims` where outputs say `6 people`.
- **Read hedges as ranges.** "Over 60 days" is true if the source says 66. Precision barely moved and recall fell, because `over 15 years` got "support" from someone's age of 19.

Each of these is recorded with its numbers in an architecture decision record, so nobody helpfully "fixes" them later.

## Measuring without fooling yourself

Four things made the headline numbers trustworthy.

**A train/test protocol.** Every rule was tuned on RAGTruth's train split, and the test split was scored exactly once. Tuning on test would inflate precision in exactly the way this tool exists to catch.

**Distrusting the metric.** Span-overlap scoring rewards accidental flags. A list marker `5.` overlapping a hallucinated list item counts as a hit even though the checker flagged it for the wrong reason. Making the checker *more correct* sometimes *lowered* measured recall. The fix was to define what counts, independently of the checker and on train only: once for the recall denominator (a labelled span must still contain a digit after list markers and "passage N" are removed), once for fault-injection targets. Both happened before the test split was ever scored.

**Auditing the "false positives".** Annotators miss things. Every test flag that missed a labelled span was audited twice by independent LLM auditors, each blind to the other and required to quote evidence from the source:

- 29 of 76 were values the source never states: a jury "of 12" the article never mentions, a restaurant "open since 1988", "30 reviews" where the source lists three.
- 31 were derived values: conversions, and review counts.
- 16 were genuine checker errors.
- The two auditors agreed on 98.7% of correct-vs-error calls (κ 0.96).

**Planting fabrications on purpose.** Human labels are a noisy guide to recall, so recall was also measured directly. In every response the annotators judged clean, one real number was changed by a single digit, which is the invented-tracking-number failure under controlled conditions.

## Results (RAGTruth test, scored once)

| | naive | hardfacts v0.1 | hardfacts v0.2 |
|---|---:|---:|---:|
| flags raised | 1,548 | 289 | **281** |
| span precision vs human labels | 0.221 | 0.737 | **0.758** |
| flags pointing at a hallucination, after audit | n/a | 0.837 | **0.861** |
| …or at any value the source doesn't state | n/a | 0.945 | **0.972** |
| planted fabrications caught | 100% | 96.2% | 96.4% |
| clean responses with a false alarm | 19.9% | 1.8% | **1.6%** |
| time per response (Python / TypeScript) | n/a | 0.9 ms / ~0.2 ms (v0.2: ~2 ms / ~0.2 ms) |

## A second dataset, and a humbling first score

A benchmark you tuned on flatters you. So hardfacts was then run, once and untuned, on FaithBench: 750 news summaries by 10 modern LLMs, deliberately chosen where existing detectors disagree. Planted-fabrication recall generalised at 95.6%. False alarms didn't: 12.0% of clean summaries were flagged, *worse* than the naive check's 10.9%.

The audit of all 85 disputed flags found the cause in minutes. FaithBench's sources are word-tokenised (`July 22 , 1947`), and a space before a comma stopped the year attaching to its date. Fixing that one general bug (with RAGTruth train unchanged) cut false alarms to 5.1% and raised span precision from 0.44 to 0.65. Those post-fix numbers are reported as a bug fix, not as a second out-of-sample result. The lesson for anyone shipping a text normaliser: your second dataset will format things your first one never did.

## The use case, measured: support agents

RAGTruth and FaithBench are news, QA and business write-ups. The case I actually built this for is a support bot stating order IDs, prices and card numbers from a tool's JSON, and neither dataset has it. τ-bench does: Sierra published real runs of GPT-4o and Claude 3.5 Sonnet as retail and airline agents, 22,179 replies, each with every tool result the agent saw.

I recorded the run before reading a single flag. Then two blind auditors classified 160 of them, and the result reframed the tool:
- **72% of the flags (115 of 160) were arithmetic.** These were fare totals, price differences and refunds the agent had computed.
- **Only 4% (6 of 160) were invented.** The inventions were exactly the target: "your gift card ending in **2692**" when the card on file is `gift_card_7250692`, a guessed user ID sent to a tool, a flight duration no tool returned.
- **24% (39 of 160) were my checker's errors, and every one was a tool-output pattern:**
  - float noise like `"amount": 3.759999999999991`, which is $3.76
  - numbers buried in IDs like `credit_card_7574394`
  - dates the user typed without a year

After those fixes, a second audit of the fixed checker found 90% arithmetic, 5% invention and 5% errors. The errors were "ending in 1784" references, since fixed.

The arithmetic mattered. Across both audits, 16 of 189 computed values were wrong: a fare difference taken against one leg of a two-leg trip, "12 options available" when only 10 were, a $35.94 refund stated as $235.94. Flagging all of it as "no source" is correct (ADR-0005), but it makes the reviewer redo the agent's search. So every unsupported number now carries a **Derivation**, the arithmetic that produces it from values the reply itself states: `$6.32 = $101.12 − $94.80`.

The obvious design searches the source data for operands. I measured it before building it. Over a few hundred prices, some sum or difference lands on almost any value, so it "explained" 62% of planted fabrications. Restricted to the reply's own supported values, Derivations explain 45% of flags, only 0.5% of fabrications get one by coincidence, and all 38 the auditors checked were real derivations. A Derivation never makes a value supported. It shows the operands, so `$282 − $177` is visibly the wrong subtraction.

One more lesson came from τ-bench. A differential run of both ports on its real tool results found 22% of turns rendered differently, because JavaScript reorders integer-like object keys and has no `1518.0`. Neither RAGTruth nor 120,000 fuzzed texts had exercised that. Python now renders the JavaScript way. Test your port on the data your users will send, not only on the data you have.

## What it can't do

The big limitation is **binding**. If the source says Gordon is worth $2.1 billion and the output gives that to Andrew, the value has provenance and the check passes. When a real source value is moved to the wrong place, hardfacts catches 22%, almost all where Kinds happen to disagree (a swapped time or date). (This write-up first said 42%; a benchmark bug counted fragment swaps as binding errors, and the deep-check audit caught it.) Binding needs real context, a parse or a model, so it belongs in the layer above. **Derived values** are flagged even when correct, but when the reply's own values produce them, the flag shows the working. It can't tell right operands from wrong ones. And prose claims are out of scope by design.

## Using it in production

Two patterns work.

1. **Verify and retry.** Check the draft, and if anything is unsupported, send the model `feedback(report)` ("these values do not appear in your sources…") and regenerate. Never send an unchecked draft. A bot that must calculate should loop on `report.unexplained` instead of `report.ok`, because its totals will always be unsupported. The repo has runnable versions for plain Python, a Pydantic AI `output_validator` and the Vercel AI SDK.
2. **Pre-filter, then sample the judge.** Run hardfacts on 100% of traffic for free and send a sample to the paid judge for prose. At a million responses a month, judging everything with Claude Haiku 4.5 costs about $2,000. Hard-fact checks on everything plus a 10% judge sample costs about $200.

## Two languages, one behaviour

The library ships in Python and TypeScript. Python is the reference. The TypeScript port is held to it in four ways:
- a shared fixture of every `check()` call in the Python test suite, including the feedback text
- a differential run over all 17,790 RAGTruth responses
- a fuzz differential
- the τ-bench differential above

All four are 100% identical. That run also surfaced a V8 regex bug: a case-insensitive modifier group, `(?i:bn|mn|…|b|t)`, silently stops matching an upper-case `B` after `\d+`, so `$2.1B` lost its "billion". The port now folds case into the pattern itself instead of trusting the engine.

---

*Code, benchmarks, audits and design records: this repository. Built and measured in one day. Every number above comes from a committed script and can be regenerated.*
