# Results

Every number here comes from a committed file in [`bench/results/`](../bench/results/) or [`bench/audit/`](../bench/audit/).


Measured on [RAGTruth](https://github.com/ParticleMedia/RAGTruth) (17,790 responses from six LLMs with human-labelled hallucination spans, MIT). Every rule was developed on the train split. The **test split is scored once per release**: v0.1 at `78413c9`, and v0.2 at `507877a` (the checker frozen at `96eaa4b`; later commits changed only docs and benchmarks) ([protocol](adr/0004-benchmark-protocol.md), [raw results](../bench/results/)).

| RAGTruth test | flags raised | span precision | hard-fact recall | response precision |
|---|---:|---:|---:|---:|
| naive baseline (every digit string must appear in the source) | 1,548 | 0.221 | 0.703 | 0.521 |
| hardfacts v0.1 | 289 | 0.737 | 0.578 | 0.833 |
| **hardfacts v0.2** | **281** | **0.758** | 0.578 | **0.850** |

- **Span precision** is the share of flags that overlap a span the annotators labelled as hallucinated. **Hard-fact recall** is the share of labelled spans containing a number (after removing list markers and "passage N" citations) that hardfacts flags.
- **Human labels undercount.** In v0.1, *all 76* test flags that miss a labelled span were audited twice, by two LLM auditors (separate Claude agents, each blind to the other, told to search the source for the value in any form). **29 are values the source never states** (a jury "of 12" the article never mentions, a restaurant "open since 1988"), 31 are values *derived* from the source (°F→°C, "based on 3 reviews"), and 16 are checker errors. Adding the inventions to the labelled hits, **83.7% of all flags point at a hallucination; counting derived values too, 94.5% point at a value the source doesn't contain.** The auditors agreed on 98.7% of correct-vs-error calls (Cohen's κ 0.96). Every verdict has a quoted piece of evidence, so any of them can be checked by hand in [the audit files](../bench/audit/test/). v0.2 raises no flag outside a labelled span that v0.1 didn't already raise, so the same verdicts carry over. **86.1% of v0.2's flags point at a hallucination, and 97.2% counting derived values** ([delta audit](../bench/audit/test-delta-8270819/)).
- **Controlled fault injection.** On the 1,732 test responses the annotators judged clean, hardfacts v0.2 **catches 96.4% of planted fabrications** (one digit of a real value changed: 1,032 plants across dates, times, money, percentages, phones and numbers). It **raises a flag on 1.6% of clean responses; the naive check flags 19.9%**. That is 12× fewer false alarms. v0.1 scored 96.2% and 1.8%. [Method](../bench/fault_injection.py) · [v0.2 result](../bench/results/fault-test-507877a.json).
- **Speed.** about 0.2 ms per response in TypeScript and about 2 ms in Python. Measured in one sitting with `bench/speed.py`, on the same loaded machine, v0.1 took 1.74 ms and v0.2 2.22 ms. The timings stored in `bench/results/` move with machine load (v0.1 recorded 0.9 ms idle), on RAGTruth prompts (2.6 KB on average) on one laptop core. An LLM judge takes seconds and costs about $0.002 a call ([worked cost model](../examples/prefilter_router.py)).

The naive baseline's higher recall comes from flagging almost every number: it raises 5.4× as many flags, and more than three in four of them touch no labelled hallucination.

### A second dataset it was never tuned on: FaithBench

[FaithBench](https://github.com/vectara/FaithBench) (Vectara, NAACL 2025; CC BY-NC-SA, downloaded for evaluation only) has 750 news summaries by 10 modern LLMs, chosen *because* existing detectors disagreed on them. It was scored once, with no tuning, at `e93d226`, and the result was weaker. It is reported here as scored:

| FaithBench | flags | span precision (vs any annotation) | planted fabrications caught | clean summaries flagged |
|---|---:|---:|---:|---:|
| naive baseline | 210 | 0.295 | 100% | 10.9% |
| hardfacts, as scored (`e93d226`) | 153 | 0.444 | 95.6% | **12.0%** |
| hardfacts after the fix below (`f6b84f4`, no longer out-of-sample) | 89 | 0.652 | 95.6% | 5.1% |

Recall on planted fabrications generalised. Precision didn't, at first. Auditing all 85 unmatched flags found 64 checker errors, nearly all one bug: FaithBench sources are word-tokenised (`July 22 , 1947`, with a space before the comma), so the year didn't attach and correct dates were flagged. The fix is general and checked against RAGTruth train, where nothing moved. Because it was found on FaithBench, the post-fix row is a bug-fix measurement, not a second out-of-sample result. The audit also found 4 inventions the annotators missed, including rugby scores the source never states. FaithBench's labelled hallucinations are mostly prose-level, so hard-fact recall there is low (0.21), which is the expected ceiling for a value-level check. [Results](../bench/results/) · [audit](../bench/audit/faithbench/)

### A third dataset, from the use case it's built for: support agents (τ-bench)

[τ-bench](https://github.com/sierra-research/tau-bench) (Sierra, MIT) publishes real runs of GPT-4o and Claude 3.5 Sonnet as retail and airline support agents: 22,179 replies, each checked against the tool definitions, policy, user turns and JSON tool results the agent had seen. There are no hallucination labels, so two blind auditors classified samples of the flags. The run was pre-registered and recorded before any flag was read. [Full record](reviews/2026-09-26-taubench.md).

| τ-bench | flags | replies flagged | planted fabrications caught |
|---|---:|---:|---:|
| naive baseline (same Sources as the last row) | 6,818 | 18.5% | 100% (by construction) |
| hardfacts, as scored (`bd9d22f`, harness corrected) | 4,322 | 11.6% | 93.1% |
| hardfacts after the fixes the audit led to (`49e677b`, not out-of-sample) | 3,411 | 8.75% | **98.9%** |

- **On support text, most flags are arithmetic.** Of 80 audited flags from the fixed checker, 74 (92.5%) are values the agent computed (fare totals, price differences), 3 are invented and 3 were checker errors, since fixed. The two auditors agreed on all 240 verdicts across both audits, but they are the same model family, so read that as consistency, not independent confirmation.
- **The inventions are the failures this tool exists for:** "the gift card ending in **2692**" when the card is `gift_card_7250692`, a guessed user ID passed to a tool, a flight duration no tool returned.
- **The arithmetic goes wrong too.** 11 of 115 audited derived values were wrong: a fare difference taken against one leg of a two-leg trip, "12 options available" when 10 are, a $35.94 refund stated as $235.94. That's why each flag carries its Derivation. 45% of flags get one, and all 38 audited ones were real derivations. Only 0.5% of caught fabrications get one by coincidence.
- **What it doesn't show:** flags don't predict task failure (48% of both successful and failed runs have one). τ-bench tasks mostly fail on wrong actions, which a value checker can't see.

### The held-out test of all that: τ²-bench, where a prediction failed

Every rule since the first τ-bench run came from reading τ-bench flags, so τ-bench can't say whether they generalise. [τ²-bench](https://github.com/sierra-research/tau2-bench) (Sierra, MIT) publishes 4,448 runs of newer agents: Claude 3.7 Sonnet, GPT-4.1, GPT-4.1-mini and o4-mini. They cover airline, retail and a new telecom domain. The checker, metrics and fail thresholds were [pre-registered](reviews/2026-09-26-tau2bench-preregistration.md) and frozen before the first score. [Results](reviews/2026-09-26-tau2bench-results.md).

| prediction | predicted | τ²-bench | |
|---|---:|---:|---|
| planted fabrications caught | ≥ 97% | **98.2%** | pass |
| flags that are checker errors | ≤ 10% | **19.7%** (telecom 39.4%) | **fail** |
| flags carrying a Derivation | ≥ 30% | 37.8% | pass |
| fabrications "explained" by coincidence | ≤ 1% | 0.99% | pass, at the limit |
| replies flagged vs naive | under half | 6.6% vs 9.8% | miss |

The recall generalised and the precision didn't. Telecom agents write things τ-bench agents never did, such as "5G/4G/3G/2G" and "your line ending in 2002", and 24 of the 31 audited errors came from four such formats. They are fixed test-first in both ports, and 25 of the 31 now clear, with every audited invention still flagged. That is a post-fix measurement, not a held-out one. The audit also found a **circular Derivation**: an invented $1,707 total "explained" as the sum of its parts, one of which the agent had computed *from* the invented total. That is why a Derivation never changes a verdict.

