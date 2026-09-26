# ADR-0008: Names are checked against same-shaped names in the Sources

- Status: accepted
- Date: 2026-09-27

## Context

Short letter-and-digit mixes (`COVID-19`, `B12`, `CD8`, `H1N1`, `Schedule 13G`) are read as names, not values. That rule is what keeps them from flooding the flags: most names an answer mentions appear in no Source at all, and flagging every one would make hardfacts cry wolf. The cost showed on RAGBench. A digit changed inside a name (`COVID-19` → `COVID-12`, `H1N1` → `H2N1`, `CD8` → `CD6`) was caught only 46% of the time (169 of 370 plants), against 96–100% for values ([results](../reviews/2026-09-27-ragbench-results.md)). In support text, the same failure is a wrong model number (`S23` for `S24`) or a wrong form (`Schedule 16G` for `13G`).

## Decision

A **name** is a token that mixes letters and digits, is not already a Claim of another Kind, and is not an amount written against a currency code (`RMB105`). A name becomes a Claim only when the Sources contain a name of the **same shape**: the same token with every run of digits replaced by `#`, ignoring case and hyphens. `COVID-12` is shaped like `COVID-19`, and `H2N1` like `H1N1`. The Claim is Supported only by the same name, ignoring case and hyphens.

A name whose shape no Source contains is not a Claim, because there is nothing to compare it against. That makes this the one Kind whose Claims depend on the Sources, and the dependence is deliberate. The question is not "does the Source mention this name?" but "the Source names something of this shape, and the answer changed its number".

## Measured before building (`bench/name_experiment.py`)

| | |
|---|---:|
| name plants caught, hardfacts before | 169 of 370 (46%) |
| caught by the name rule alone | 186 of 370 |
| caught by either | **355 of 370 (96%)** |
| correct RAGBench responses newly flagged | **1 of 10,125** (TNM stage `N1` against `N0`) |
| clean RAGTruth test responses newly flagged | **0 of 1,757** |

A broader version that also re-checked tokens hardfacts already claims ("5-year", "260C", CVE numbers) flagged 13 correct RAGBench responses and 14 clean RAGTruth ones, all duplicates of existing Claims. So the rule covers only what nothing else checks.

## Consequences

- There is a new Kind, `name` ("name with a number"). Callers passing `kinds` opt in or out as with any other Kind.
- A name the Sources never mention in any form still passes. An invented product code with no sibling in the Sources is outside this rule, as before.
- Coincidental siblings can mislead in either direction. `N1` next to `N0` is flagged even when both stages are real and only one was retrieved. A Source that lists `CD4` makes an unrelated, correct `CD8` a Claim, which is still Supported if `CD8` appears anywhere.
