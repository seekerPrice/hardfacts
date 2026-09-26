# ADR-0001: Build `hardfacts`, a deterministic provenance checker for LLM output

- Status: accepted
- Date: 2026-09-26
- Decider: Claude, with the choice delegated by the maintainer

## Context

LLM applications that answer from data (support bots, RAG assistants, agents with tools) fail most expensively on specific values: a tracking number, an amount, a date, a card's last digits. A drafting model inventing a plausible shipping tracking number is the canonical case. The common guards are an LLM judge, which is slow, costs money on every call and can itself be wrong, or a naive "every number must appear in the context" string check, which is too noisy to leave on. No small, deterministic, *measured* library covered that failure class.

## Decision

Build `hardfacts`, an open-source Python library with zero runtime dependencies. Given an LLM output and the sources the model was given, it extracts every **hard fact** (quantity, percent, money, date, time, phone, email, URL, identifier), normalises each one, and reports every claim that no source supports, with the evidence for the claims that are supported.

Benchmark it against RAGTruth's human span labels (MIT, 17,790 responses from 6 LLMs). Rules are tuned on the train split only, and the test split is reported once.

Feasibility was checked before this decision, against RAGTruth train/test statistics:
- Hallucination spans containing a digit: 44% of QA, 22% of summary and 13% of data-to-text spans.
- A naive "every digit string must appear in the source" check had 19–30% span precision on the test split. The false positives are almost all fixable structural cases: list enumerators, "summary in 88 words" meta-claims, `21:0` vs `9:00 PM` hours, and `4.0` vs `4-star` ratings. Engineering that gap from 19% to a high number is the project.

## Strongest argument against

"Check that numbers in the answer appear in the context" is a known heuristic. Langfuse's hallucination-detection guide lists it as a free pre-screen, so a reviewer may call it regex. The rebuttal has to come from the artifact itself:
(a) measured precision and recall against human labels, with a train/test protocol;
(b) typed normalisation that a regex can't do, such as `21:0` ≡ `9 PM`, `$2.1 billion` ≡ `2,100,000,000`, `RM1.2k` ≡ `1200 ringgit` ≡ `一千二百令吉`, and partial-date semantics (`February 7` is supported by `7 Feb 1945`, but `February 7, 2022` is not);
(c) the production pattern: a free pre-filter that sends only flagged outputs to a paid judge, with the cost maths.
If the benchmark can't show (a), the project fails honestly and the write-up says so.

## Consequences

- A public, runnable library, written from scratch.
- It is released on GitHub first. PyPI and npm packages follow when the repository shows demand (see the README).
