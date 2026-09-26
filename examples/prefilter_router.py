"""Route every response through hardfacts, and only a sample through a paid LLM judge.

    uv run python examples/prefilter_router.py

hardfacts doesn't replace a judge. It can't read prose claims ("the hotel has a
pool"). What it does is take the most damaging class, invented IDs, amounts, dates
and contact details, off the judge's plate. That class then gets checked on 100%
of traffic for free and deterministically, and the judge budget goes where
only a judge helps.

Prices are the published Claude Haiku 4.5 API rates as of 2026-09-26 ($1 / MTok
input, $5 / MTok output, platform.claude.com/docs/en/about-claude/pricing). Token
counts use the RAGTruth averages measured in this repo: 3,780-char prompt and
732-char response, at ~4 chars per token. Check your own rate card and traffic
before quoting these numbers.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from hardfacts import check, feedback

HAIKU_INPUT_PER_MTOK = 1.00
HAIKU_OUTPUT_PER_MTOK = 5.00
JUDGE_PROMPT_TOKENS = 250          # rubric and instructions (assumption)
JUDGE_VERDICT_TOKENS = 120         # short JSON verdict (assumption)
SOURCE_TOKENS = 3780 // 4          # measured average, RAGTruth prompts
RESPONSE_TOKENS = 732 // 4         # measured average, RAGTruth responses


def judge_cost_per_call() -> float:
    tokens_in = JUDGE_PROMPT_TOKENS + SOURCE_TOKENS + RESPONSE_TOKENS
    return tokens_in / 1e6 * HAIKU_INPUT_PER_MTOK + JUDGE_VERDICT_TOKENS / 1e6 * HAIKU_OUTPUT_PER_MTOK


@dataclass
class Decision:
    action: str      # "retry" (fix before sending) | "judge" (send to the paid judge) | "pass"
    reason: str


def route(output: str, sources: list, judge_rate: float, rng: random.Random) -> Decision:
    report = check(output, sources)
    if not report.ok:
        return Decision("retry", feedback(report))  # deterministic, free, and the fix is known
    if rng.random() < judge_rate:
        return Decision("judge", "sampled for prose-level review")
    return Decision("pass", "every hard fact has a source")


def monthly_cost(responses: int, judge_rate: float) -> float:
    return responses * judge_rate * judge_cost_per_call()


if __name__ == "__main__":
    rng = random.Random(0)
    record = {"tracking": "EN123456789MY", "eta": "2026-10-03", "fee": 12.90}
    for draft in ("Tracking EN123456780MY, arriving 3 October.", "Tracking EN123456789MY, arriving 3 October."):
        d = route(draft, [record], judge_rate=0.10, rng=rng)
        print(f"{d.action:<6} ← {draft}")

    print(f"\njudge cost per call (Haiku 4.5): ${judge_cost_per_call():.5f}")
    print(f"\n{'responses/month':>16} {'judge 100%':>12} {'hardfacts + judge 10%':>22}")
    for n in (100_000, 1_000_000, 10_000_000):
        print(f"{n:>16,} {'$' + format(monthly_cost(n, 1.0), ',.0f'):>12} {'$' + format(monthly_cost(n, 0.10), ',.0f'):>22}")
    print("\nhardfacts itself: ~2 ms (Python) or ~0.2 ms (TypeScript) and $0 per response, on 100% of traffic (bench/ragtruth.py measures the time).")
