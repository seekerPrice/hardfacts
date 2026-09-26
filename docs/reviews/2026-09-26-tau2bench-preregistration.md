# Pre-registration: hardfacts on τ²-bench

Written and committed before any τ²-bench Output was checked. τ²-bench is the held-out test of everything τ-bench taught this project. Every rule added after the first τ-bench run came from reading τ-bench flags, so τ-bench can no longer tell whether those rules generalise.

## What is fixed in advance

- **Checker:** the commit named in the "Frozen at" line below. No rule changes between that commit and the scored run.
- **Data:** τ²-bench (Sierra, MIT) at `b7ea907`, fetched by `bench/fetch_tau2bench.sh`. It is one published run per agent and domain: Claude 3.7 Sonnet, GPT-4.1, GPT-4.1-mini and o4-mini, each in airline, retail and telecom, for 12 files. That is 4,448 simulations and about 46,000 agent turns with text. The only thing inspected before scoring was the file format: turn and source counts, with no check run.
- **Method:** `bench/tau2bench.py`, which is `bench/taubench.py`'s method. The Sources are the domain's `tools.py`, the policy, the user's turns, and the tool results the agent requested. Results of the telecom user's own device tools are excluded, because the agent never sees them.
- **Metrics:**
  - turns flagged, against the naive check
  - fabrications caught (fault injection, as on τ-bench)
  - the share of flags carrying a Derivation, and the share of caught fabrications that get one by coincidence
- **Audit:** 120 flags, 10 per file, seeded (`--seed 0`), each classified by two blind auditors with the τ-bench protocol (`bench/taubench_audit.py`).

## Predictions (from τ-bench, where the rules were developed)

| metric | τ-bench (dev) | prediction for τ²-bench | fails if |
|---|---:|---:|---|
| planted fabrications caught | 98.9% | ≥ 97% | < 95% |
| audited checker errors (missed_support + not_a_claim) | 5.1% | ≤ 10% | > 15% |
| flags carrying a Derivation | 45% | ≥ 30% | < 20% |
| caught fabrications given a Derivation by coincidence | 0.5% | ≤ 1% | > 2% |
| turns flagged, hardfacts vs naive | 8.8% vs 18.5% | fewer than half of naive's | more than naive's |

Telecom is new in kind: device states, data plans and troubleshooting steps. Its checker-error share is predicted separately to be at most 20%, and it is reported on its own.

## What happens after

The numbers are reported as they come out, whatever they are. Checker errors the audit finds may then be fixed, but any run after a fix is labelled post-fix and is not out-of-sample. A missed prediction is reported as a miss, with the cause.

Frozen at: checker `96eaa4b` (after hostile-review round 6; `tools/verify.sh` passed on it). Scored once, from this commit's successor, which changes only this line.
