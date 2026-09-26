# Deep-check audit, 26 September 2026

An adversarially verified bug audit of the whole project at `9b0c867`, run with the `deep-check` skill's manual fallback.

- **Four independent finders**, one per module group. Each hunted with runnable probes. The groups were:
  - A: the Python extractor
  - B: the matcher, CLI and report
  - C: the TypeScript port's fidelity
  - D: the benchmark's own metrics
- **Three independent refuters per group.** They covered:
  - reachability: can it happen through the public API?
  - mitigation: is it intended, documented or excused?
  - citation: is the mechanism real and the severity demonstrable?

A candidate had to survive all three refuters to count as confirmed. Where the refuters split, the candidate was demoted and is shown below, not dropped.

**Result: 69 candidates. 62 were confirmed by all three refuters, 6 were split and demoted, and 1 was refuted by two.** Every confirmed finding was fixed test-first (`tests/test_deep_check_regressions.py`, plus the CLI and report tests) in both languages, or deliberately left as a documented limitation. Parity was re-verified after each batch: conformance fixture, RAGTruth differential including spans, and a fuzz differential with non-BMP input. So was the train regression gate.

## The finding that mattered most: a benchmark metric

**D-bench-1.** The fault-injection "swap" mutation (a real source number moved to the wrong place, i.e. a Binding error) drew raw digit fragments. It would plant the `1` from `$2.1 billion`, for example. So about a quarter of "swaps" were really fabrications, and the published binding catch rate of **42% was overstated**.

After fixing the harness to swap whole numbers of the same shape, the release checker (`78413c9`, pinned via `PYTHONPATH`) catches **21.6%** of binding swaps on the test split. Fabrication recall is 96.2% and the clean-flag rate is 1.8%. The naive check now catches 0% of swaps, which is what a binding test should show. The README, write-up, ADR-0006 and demo page were corrected. ADR-0006's unit-agreement experiment was re-measured: 18.6% → 30.2% swap recall, precision 0.718 → 0.596. The decision was unchanged.

## Resolution by batch

| Batch | Findings | Resolution |
|---|---|---|
| Bench honesty | D-bench-1 (swap fragments), D-bench-2 (`commit()` never marked a dirty tree), D-bench-5 ("3.8 KB" sources: mean is 2.6 KB), D-bench-6 (stale fixture count) | fixed; results re-recorded on pinned checkers (`*-pinned.json`) |
| Extractor 1 | A1 ISO datetimes lost their hour and read the `+08:00` offset as a time · A2 CJK amounts dropped leading thousands groups · A3 `RM20 T-shirt` read as RM 20 trillion · A4 non-breaking spaces · A5 dot/space-grouped numbers read as phones · A6 unformatted phones · A7 all-digit tracking numbers weren't identifiers · B-01 `#48213` ≠ 48213 · A8 `9.30am` · A10 `out of 10,000` · A11 CJK idioms swallowing numerals · A15 `1,000°F` · A21 character limits exempted · A24 full-width digits · A27 `Rp 50.000` | fixed |
| Extractor 2 | A9 `16:9` switching a text to the 24-hour clock · A12 `一点五亿`, `一万亿` · A16 `3 Oct 26` read as Oct 26 · A17 `3-Oct-2026` · A18 `3–5 October` · A19 `3hb Oktober` · A20 `between fifteen and twenty` · A22 `5 Mac laptops`, `May 5%` · A23 quadratic URL regex (40 KB: ~20 s → ms) · A26/B-02 stale ADR-0003 example | fixed (A9's timestamp half was refuted as intended) |
| API / CLI / port | B-03/C3 floats rendered as `5e-05` · B-04 a bare string as `sources` iterated characters · B-05, B-07 report input edge cases · B-06 unparseable `.json` · B-08 `--fail-over nan` · B-09/C8 an empty `--kinds` passed silently · B-10/C7 28-digit rounding · B-11/C4 CRLF/BOM offsets · C1 TS CLI rounded integers beyond 2^53 · C5 JS multiline anchors at `\r`/U+2028 · C6 surrogate pairs · C2/D3 parity tests never compared spans | fixed; spans now compared, in code points |

## Demoted (split verdicts) and refuted

- **A25** (short voucher codes like `SAVE20` are treated as names): split. It's a measured design choice (ticket 08, precision 0.43 → 0.68). It's kept, and listed in the README limits because a support bot can invent a voucher code.
- **A9, A10, A12**: partly refuted. Only the confirmed halves were fixed.
- **B-12** (dict Sources with `date`/tuple keys crash): refuted. Such Sources are outside the "JSON-like" contract. Keys are now `str()`-ed anyway.
- **C2** (spans in UTF-16 vs code points): split. Refuted as a defect, since each port's spans slice its own strings. The documentation and test gap was fixed.
- **D-bench-4** (plants already flagged before mutation): refuted, 0.03 pp.
- **D-bench-7** (FaithBench annotation vs span counting): refuted. The number is unchanged at 0.21.

## Deliberately left as limitations (README)

- A13: dates and years written in Chinese numerals (`二〇二五年十月三日`).
- A14: signs. `-5°C` and `5°C` share a Value, because a leading `-` is as often a dash as a minus. U+2212 is now read like `-`.
- A28: Indian lakh grouping (`₹1,50,000`).

## Verification after the fixes

- Python: 156 tests. TypeScript: 175 tests. Conformance: 164/164 cases.
- RAGTruth differential: 17,790/17,790 identical, spans included. Fuzz differential: 40,000 texts identical, spans included, with emoji, `\r` and U+2028.
- Train gate: span precision 0.719, hard-fact recall 0.544, fabrications caught 0.944, clean flags 0.021. All unchanged or better.

## Round 2: a hostile review of the fixes

Two more independent reviewers attacked the fixes themselves, each starting from the rule that a fix is wrong until it survives an adversary:

- **Python.** Every probe was run against the pre-fix tree (`9b0c867`) and the fixed tree.
- **TypeScript.** About 217,000 generated `check()` cases, every shipped pattern against its Python original, and 150,000 float renderings.

**The Python reviewer found 16 regressions in the round-1 fixes: 5 high, 7 medium, 4 low.** The train gate had passed through every one of them, because RAGTruth (English news, QA and Yelp) contains almost no:

- sub-cent prices
- US dotted phones
- whitespace-aligned tables
- Malay
- 10-digit integers in JSON

A green gate showed only that the fixes were safe on RAGTruth.

| ID | Regression the round-1 fix caused | Fix (test-first, both ports) |
|---|---|---|
| H1 | Splitting number-word runs was cubic: 6 KB of "one and …" took 26 s | a run splits only at an article, "and" or an ordinal, and a phrase is at most 12 tokens (the same input: 13 ms) |
| H2 | 10+-digit integers became IDs, so `$2.5 billion` lost support from `{"market_cap": 2500000000}` | all-digit IDs support amounts, and amounts support all-digit IDs |
| H3 | One dot after any currency meant thousands: `$0.125` read as 125, which falsely supported `$125` | dot-thousands only for IDR and VND (and after `rupiah`, `dong`, `₫`), never for a leading `0.` |
| H4 | `800.555.0199` and `212 555 0199` were no longer phones, so a changed last group went unseen | the 3-3-4 and 1-3-3-4 shapes are phones without a cue word |
| H5 | "Earliest date wins" let a count steal a month-first date (`3  Oct 26, 2025` in a table) | of overlapping readings, the one stating more parts wins; a two-digit year never comes before a four-digit one |
| M1 | `+60123456789` and the WhatsApp `wa_id` `60123456789` stopped matching (phone vs ID) | phone digits match ID and quantity Evidence in both directions |
| M2 | Malay `5 Mac` (5 March) needed a year | `Mac` is March unless an Apple noun follows |
| M3 | `2 malam` (two nights) read as 20:00; `12 malam` read as noon | Malay day-parts are times only after `pukul`/`jam` or with minutes; `12 malam` is midnight |
| M4 | `$5K-$10K` read as `$5` | a hyphen before a currency is a range, not a word |
| M5 | `3 March, 45` read 45 as the year 2045 | no two-digit year after a comma |
| M6 | "nineteen ninety nine" and "Seven Eleven" became two numbers | juxtaposed number words yield nothing unless the run has a connector |
| M7 | `example.com.au` gave no URL, so a made-up `.com.au` domain passed | second-level country domains are recognised; `HP.com.Click` backs off to `HP.com` |
| L1 | `十一点五十分` (11:50) read as 11.5 | Chinese clock times (`点…分`, `点半`, `点一刻`) are times |
| L2 | `+12500000 this month` read as a phone | a bare `+number` needs a cue, or 10+ digits with no word after it |
| L3 | `#00123` was supported by `#123` | IDs compare as strings |
| L4 | `3 Oct 85` read as 2085 | the POSIX pivot: 69–99 → 19xx |
| A5 (rest) | `Hubungi kami: Rp 1.500.000` was still a phone | a number right after a currency is never a phone |

**Fixing these introduced one more regression, and the claim diff caught it.** "a sixteen dollar glass" stopped supporting `$16`, because the M6 rule also blocked runs that start with an article. It was found by diffing every Claim on all of RAGTruth before and after the change, and fixed test-first. The final diff against round 1 shows no new flags, and two false flags removed: `HP.com`, and `$550-1200/night` read as a phone.

**The TypeScript reviewer found 15 divergences between the ports.**
- **Fixed in both ports:** the cue window's character counting, BigInt number words, ASCII-only decimal points, `anchored()` with a lone surrogate, integral-float Sources (through H2), an iterative renderer for deeply nested Sources, and lone surrogates in `--json` output.
- **Fuzzer found a crash:** a mixed `1五点半` crashed both ports' new clock-time pattern. It is now a test.
- **Documented instead:** the inherent differences, which are span units, JSON floats and key order, the 1,000-digit context, CPython's 4,300-digit integer limit, the Unicode version, and CLI argument parsing. See [port-parity.md](../port-parity.md).
- **Harness gaps closed:**
  - The fuzz differential now compares rendered Sources and every piece of Evidence. It also normalises Values in the library's exact context.
  - The fuzz alphabet covers the round-2 constructs.
  - The conformance test compares spans in code points.

### Verification after round 2

- Python: 178 tests. TypeScript: 243 tests, with a 232-case conformance fixture.
- RAGTruth differential: 17,790/17,790 identical, spans included. Fuzz differential: 3 seeds × 40,000 texts identical, Sources and Evidence included.
- Train gate: span precision 0.720, hard-fact recall 0.544, fabrications caught 0.944, clean flags 0.021.

## Round 3: a hostile review of the τ-bench-era changes

Everything added after round 2 went through the same process: two more reviewers, each probing the pre-change tree (`bd9d22f`) against the new one. That covered booking codes, float-noise rounding, ID segments, year-less dates, ordinal ranges, Derivations, last-digit references, JavaScript-order rendering and the regex rewrites.

**The Python reviewer found 13 regressions (6 high, 4 medium, 3 low). The TS reviewer found 4 more high findings, one of them a divergence between the ports.** Once again the train gate passed through all of them.

| ID | Regression | Fix |
|---|---|---|
| H1 | Derivation work was bounded per flagged value only: 45 KB of Output took 175 s | a lookup-and-prune search (identical results on 58,152 flags), and at most 200 values searched per check |
| H2 | the card-mask regex was quadratic: 50 KB of `*` took 10 s | masks are found as maximal runs, then the digits are read in code (8 ms) |
| H3, H4 | a year-less date took *any* year from *any* Source. `{"appointment": "August 5", "created_at": "2023-…", "now": "2024-07-30"}` supported "5 August **2023**" | only the conversation's year is lent: a date introduced by *current time*, *today*, *now* or *as of* |
| H5 | **Markdown bold was read as a card mask**: "Take **500** mg" was supported by "1500 mg" | a mask needs 3+ characters, digits followed by `*` are bold, and "last N **digits**" is required |
| H6 | 4-digit ID segments supported amounts: "$2,500" was supported by `ORD-2500` | segments need 6+ digits and never support money or percentages |
| M1 | Derivations mixed currencies (`$60 = €100 − $40`) | operands must share the target's currency family |
| M2 | "your plan ends in 2025" became a card suffix | a year next to "ends" or a time noun is a year |
| M3 | a Source's "May 19 and 20" didn't support "May 19th and 20th" | Sources read unordinal ranges generously, and the second day also vouches for its number |
| M4 | "card ending in 500" was supported by a price of 1500 | suffixes need ID or phone Evidence, the digits themselves, or a 7+ digit account number |
| L1–L3 | 14-digit decimals rounded as float noise; `LLAMA3` read as a booking code; "2nd and 3rd place" read as a date | noise needs 15+ significant digits; a code ending in a digit needs a booking word; ranks are excluded |
| TS-1 | the pruning multiplied in Python's 28-digit context, so sums of 29+ digit amounts differed from TS | exact multiplication |
| TS-2, TS-4 | the float-noise pattern and `\s*:?\s*` were quadratic on long input | a length guard, and an unambiguous `(?:\s*:)?\s*` |

The fixes caused two regressions of their own, and the τ-bench flag diff caught both:
- `9MRJD4`, deep in a Source's reservation list, beyond the cue window.
- "gift card ending in 803", a 3-digit ending of an ID.

Sources now read codes without a cue, and IDs accept 3-digit endings. The TypeScript typechecker also caught a port bug: the recogniser's `words` argument would have landed in `inSource`, so every Output would have been read with Source generosity.

**One process failure, recorded here.** A commit went in with a failing conformance case, because the check chain tested grep's output rather than npm's exit code. It was fixed in the next commit. `tools/verify.sh` now runs every gate under `set -euo pipefail`.

### Verification after round 3

- Python: 221 tests. TypeScript: 338, with a strict 324-case conformance fixture that includes `feedback()` text.
- Differentials, all identical, spans included:
  - RAGTruth: 17,790/17,790
  - fuzz: 3 × 40,000, including derivation-heavy replies
  - τ-bench: 3,000/3,000 real turns
- Train gate: precision 0.721, recall 0.544, fabrications 0.944, clean flags 0.020. The stricter year rule re-flags 7 RAGTruth dates whose year the source never states.
- τ-bench: 3,411 flags, 98.8% of fabrications caught, and 45.2% of flags carry a Derivation.

## Round 4: a hostile review of the round-3 fixes

**6 high, 3 medium and 5 low findings. Most were over-corrections**: a round-3 fix aimed at one false flag, drawn too wide.

| ID | Over-correction in round 3 | Fix |
|---|---|---|
| H1 | "A six-character code ending in a digit needs a booking word" (round 3's fix for `LLAMA3`) silenced invented record locators in lists and tables. On τ-bench, 65 of 65 mutated codes had been flagged; after the change, 0 were. | only *name-shaped* codes need the word: exactly one digit, at the end (`LLAMA3`, `PIXEL8`) |
| H2 | "Your Visa card ends in 2024" was read as a year | the nearer noun decides: the card word or a time noun |
| H3 | the Source-side range rule let "March 10-12" vouch for "12 speakers" | only word-joined ranges ("May 5 and 6") vouch for their second day |
| H4 | float dict keys rendered unlike `json.dumps`, so the ports disagreed | `{1e20: …}` renders `"1e+20"`, as `json.dumps` and JavaScript do |
| H5 | "last 4 digits of" plus whitespace backtracked quadratically (4 s in TS) | each run of spaces has one owner in the pattern |
| H6 | Derivation cost was bounded per value, not per check (5.7 s in TS on 43 KB) | operands are grouped once per Kind and currency, and one 200,000-unit work budget, counted identically in both ports, bounds the check. 140 ms, and results identical to the original search on 40,541 flags |
| M1–M3 | bold card references and two-character masks weren't read; `current_date`, `currentDate` and "it is currently" didn't lend their year | read |

Also fixed in this stretch, and found by running the Claude Code hook over 300 of the maintainer's sessions: LLMs wrap URLs in Markdown (`**https://…/637**`), cite "PR #3337" from a tool's `…/pull/3337`, and shorten or lengthen git hashes. URLs now shed a trailing `*` or backtick, digits in a URL path are stated numbers (never amounts), and two lowercase hex hashes support each other by prefix.

After round 4, `tools/verify.sh` passes: all tests, all three differentials and the train gate (precision 0.721, recall 0.544, fabrications 0.944, clean 0.020). On τ-bench: 3,411 flags, 98.9% of fabrications caught.

## Round 5: a hostile review of the round-4 fixes and the URL and hash rules

**5 high findings from the batch, 1 high that predated it, 2 medium and 4 low.** There were no Python/TypeScript divergences: in 171 checks that exhausted the Derivation work budget mid-search, both ports stopped at the same place.

| ID | Finding | Fix |
|---|---|---|
| H1 | digits in a Source URL path supported plain counts: "removes 250 lines" passed against `…/pull/250` | URL path numbers support only ID references ("PR #250"), compared as strings |
| H2 | an Output hash *longer* than the Source's passed (`33e41b9670c2…` against `33e41b9`), as did any lowercase hex token | the Output may only be the shorter, less specific one |
| H3 | "currently" lent a status date's year ("order currently estimated 2023-12-01") | anchors are "current time/date", "today", "it is currently", a `now:` key and "as of" |
| H4–H6 | **matching compared every Claim with every piece of Evidence.** 50 KB of day ranges took 36 s; the Claude Code hook took 10 s on 8 MB of Sources | an index, described below |
| M1 | `BASE64`, `UINT32`, `SAVE20` were read as booking codes | letters followed by 1–2 digits is a name unless a booking word is near ("flight XEHM82") |
| M2 | "the free trial on your account ends in 2025" became a card suffix | a time noun wins unless a card is named |
| L1–L4 | a stale README size; "March 10 to 12" still vouched for "12"; Markdown variants; `*** 1500 ***` | README corrected; "to" doesn't vouch; the rest recorded |

**The index.** Each piece of Evidence registers keys, and each Claim looks up only the keys it could match. The keys are:
- its numbers
- the last 7 digits of phone-like values
- dates by their most specific stated parts
- hosts, URL path numbers and hash prefixes
- suffix digits and exact IDs

Each key was derived from a branch of `supports()`, so any pair `supports()` would accept shares one. That argument alone isn't trusted. `bench/index_differential.py` runs every case both indexed and brute-force and compares the full Reports: **43,675 identical** across RAGTruth, τ-bench, fuzz and the fixture. It now runs in CI and `tools/verify.sh`. 50 KB of day ranges went from 36 s to 0.34 s (TypeScript: 120 ms). That doesn't make matching linear, though, and round 6 showed why: when a value recurs thousands of times, every Claim really is supported by every recurrence.

Measuring for H6 also exposed a false claim in the hook's README: "about half a second". The real figure is 2.3 s on a 14 MB transcript, almost all of it reading the Sources. The README now states that.

## Round 6: a hostile review of round 5, and of the index above all

**The index held.** No input, in either port, made it disagree with brute force: about 30,000 targeted cases, 63 hand-built edge cases, and every branch of `supports()` checked against the keys by hand. The rest:

| ID | Finding | Fix |
|---|---|---|
| H1 | **a crash**: the index read every quantity's digits, and CPython refuses to turn a 4,300+-digit integer into a string. `check("x 5 y", ["1" + "亿"*600])` raised | quantities over 20 digits have no digit string (no phone or account number is longer) |
| H2, H4 | "an index makes matching linear" was false: 3,000 "5 units" against 3,000 "$5" is 9 million *true* matches, so the Report itself is quadratic (TS ran out of memory at 50 KB) | Evidence is capped at 10 per Claim, first in Source order, and the scan stops at the cap. One piece of Evidence is enough to support a Claim. The suffix key no longer lists short quantities that can never match |
| H3 | (older, TS only) float noise rounded twice through a recursive `dec()` | rounded once, as in Python |
| H5 | any URL path number vouched for any `#N`: an image's `/w/1500/` supported "Invoice #1500" | only a resource's number: `/pull/`, `/issues/`, `/orders/`, `/tickets/`, `/invoices/` and similar |
| H6 | the hash prefix rule applied to 8-character order codes | the Source hash must be 12+ characters |
| M1–M3, lows | "card's promotional period ends in 2025"; more ways of saying now; "trip" matched inside "triple" | the nearer of card word and time noun decides; anchors added; cues are whole words |

After round 6 the checker was **frozen** for the pre-registered τ²-bench run (`96eaa4b`).
