# τ²-bench results against the pre-registration

The [pre-registration](2026-09-26-tau2bench-preregistration.md) fixed the checker (`96eaa4b`), the data, the metrics and the fail thresholds before any τ²-bench Output was checked. The run was scored once (`76d7a30`, [results](../../bench/results/tau2bench-e20e892.json)), and 120 flags were then audited blind by two auditors ([audit](../../bench/audit/tau2bench/)). This page reports what came out. Nothing in `src/` or `ts/src/` changed between the freeze and the audit.

**Two of the five predictions failed.** Both failures have the same cause: the τ-bench-era rules don't cover telecom's vocabulary or a few date and reference formats that τ-bench never produced.

## Scorecard

| metric | τ-bench (dev) | predicted | τ²-bench | verdict |
|---|---:|---:|---:|---|
| planted fabrications caught | 98.9% | ≥ 97% | **98.2%** (airline 98.9, retail 97.4, telecom 100) | **pass** |
| audited checker errors, share of flags | 5.1% | ≤ 10% | **19.7%** (raw count 31 of 120) | **fail** (> 15%) |
| … telecom alone | – | ≤ 20% | **39.4%** (raw 22 of 40) | **fail** |
| … airline and retail | 5.1% | ≤ 10% | 14.2% (raw 9 of 80) | miss, inside the fail threshold |
| flags carrying a Derivation | 45% | ≥ 30% | **37.8%** | **pass** |
| caught fabrications given a Derivation by coincidence | 0.5% | ≤ 1% | **0.99%** (airline 1.6%) | pass, at the limit |
| turns flagged, hardfacts vs naive | 8.8% vs 18.5% | under half of naive's | **6.6% vs 9.8%** | miss, inside the fail threshold |

Checker-error shares are weighted by each file's share of all 5,397 flags, since the sample takes 10 flags from each of 12 files. τ-bench's 5.1% was computed the same way. The raw counts are given alongside because the weighting moves the headline by six points.

The turns-flagged miss has a mundane cause. The naive check flagged far fewer τ²-bench turns (9.8%) than τ-bench turns (18.5%). The main reason is that τ²'s agents restate tool values more literally, which leaves less for any checker to flag. In airline, hardfacts flagged slightly *more* turns than naive (11.2% vs 11.0%). That is what the pre-registered fail condition describes, though only in one domain and not overall. The cause is that naive matching accepts a number found anywhere in a Source, including inside a longer number, while hardfacts doesn't.

## What the 120 audited flags are

| verdict | count | share of flags (weighted) |
|---|---:|---:|
| derived: arithmetic over values the agent had (63 of 71 with correct arithmetic) | 71 | 67.7% |
| invented: the Sources never state it | 18 | 12.6% |
| missed support: the Sources state it and the checker missed it | 20 | 19.7% (together with not-a-claim) |
| not a claim: a menu label or an illustrative placeholder | 11 | |

Two auditors (separate Claude agents, blind to each other and to the checker's Derivations) agreed on 119 of 120 verdicts, κ 0.986. On correct flag vs checker error they agreed on all 120. Both are the same model family, so read the agreement as consistency, not as ground truth.

**Derivations.** 42 audited flags carried one. 40 were judged derived. The other 2 are false explanations:
- **Coincidence:** "Most cloud services work well with 10–20 Mbps" got `20 = 25 − 5` from two other bandwidth figures in the same reply. General knowledge in telecom replies is dense with small numbers, so a coincidental operand pair is easy to find.
- **Circular:** "the total cost … is $1707. After applying your certificates ($1000) and gift cards ($327), the remaining…" The $1707 is invented: the real fares sum to $2,613. The agent then computed the $380 remainder *from* the invented total, so `$1707 = $327 + $380 + $1000` holds. The equation is true, but it explains nothing. ADR-0007 takes operands from the Output. It doesn't consider that an operand can itself be computed from the value being explained. This is a real hole, not a sampling accident. See "Open" below.

## The checker errors, by cause

Every one of the 31 reproduces at the frozen checker.

| cause | count | example |
|---|---:|---|
| Slash-joined network generations read as one identifier | 13 | "5G/4G/3G/2G Auto" → `5G4G3G2G` |
| A Source URL keeps the sentence's full stop before a closing quote | 4 | `“http://mms.carrier.com/mms/wapenc.”` |
| "line ending in 2002" is not read as a last-digit reference | 5 | against `"phone_number": "555-123-2002"` |
| Numeric month/day dates (`05/22`, `5/19`) read as two numbers | 2 | against `2024-05-22` |
| A day range with a trailing year loses the year | 1 | "May 27 and 28, 2024" → `XXXX-05-27`, with 28 and 2024 as bare numbers |
| An ellipsis between the cue and the digits | 1 | "gift card ending in …1863" |
| An order-ID prefix added to a number the user typed | 2 | "#W9502126" against the user's "9502126" |
| A slash-joined spec | 1 | "i5/32GB/256GB" |
| An illustrative placeholder | 2 | "for example `#W0001234`" |

Four causes account for 24 of the 31 errors: slash-joined generations, URL punctuation, last-digit cues, and numeric dates. None of them is exotic. τ-bench's airline and retail agents never wrote "5G/4G" or "line ending in", so the rules were never tested on them. That is the gap a held-out set is for.

## What happens next

As the pre-registration says, checker errors found here may be fixed, and any run after a fix is labelled **post-fix** and is not out-of-sample. The numbers above stay as the held-out result. Post-fix numbers are reported in the [README](../../README.md) and [CHANGELOG](../../CHANGELOG.md), labelled as post-fix.

## Open

- **Circular Derivations.** When a reply computes a remainder from an invented total, the total gets "explained" by the remainder. In the audited case the $380 is even Supported, because it is the result of the agent's own `calculate` tool call, and the invented $1707 was that call's input. So "refuse Unsupported operands" would not catch it. A fix would have to know that a Source was produced *from* the Output's value, which means tracking tool-call provenance, and hardfacts sees only text. Until then, a Derivation shows the reviewer arithmetic that holds, not proof that the total is right. The docs already say a Derivation never changes the verdict. This case shows why that rule has to stay.
- **Telecom general knowledge.** Replies full of typical figures ("25 Mbps for 4K") are Claims with no Source. They are correctly Unsupported, but they are noise to a reviewer. hardfacts has no notion of general-knowledge numbers, and adding one would weaken the "a number with no Source is flagged" guarantee. This is left as a known cost.

## Post-fix (not out-of-sample)

The fixes (`c199d5c`), narrowed by a seventh hostile review (`33f7704`), were re-scored as `tau2bench-33f7704-postfix.json`:

| | held-out (`96eaa4b`) | post-fix (`33f7704`) |
|---|---:|---:|
| flags | 5,397 | 4,859 |
| replies flagged (naive 9.8%) | 6.6% | 5.6% |
| telecom replies flagged | 966 | 570 |
| planted fabrications caught | 98.2% | 98.2% |

Of the 31 audited checker errors, 25 clear. All 18 audited inventions and all 71 derived values are still flagged. The six left are:
- 2 order-ID prefixes (`#W9502126`) and 2 placeholders, which were never fixed.
- "(MCO→MSP 5/19)": a numeric date now needs a date word before it, because the review showed that "3/16 inch" in a Source vouched for "March 16".
- "i5/32GB/256GB": a model name keeps a spec one identifier, because the review showed "i7/16GB/1TB" passing against "i5/16GB/1TB".

Both are deliberate trades of a missed support for a caught invention (ADR-0003 applies to doubt, not to known holes).
