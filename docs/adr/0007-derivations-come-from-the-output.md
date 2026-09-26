# ADR-0007: Unsupported values are explained by arithmetic over the Output's own Supported values, never over the Sources

On tau-bench, support agents answering from tool results produce Unsupported Claims that are mostly derived. A blind double audit of 160 flags found 72% sums, differences and multiples of Source values (fare totals, price differences, refunds), and 11 of those 115 had the wrong arithmetic. ADR-0005 keeps them Unsupported, which is right, but a bare flag on `$6.32` makes the reviewer redo the search the agent did. So each Unsupported number, amount or percentage carries a **Derivation** when one exists: `$6.32 = $101.12 − $94.80`.

The operands come only from Claims in the same Output that are themselves Supported. This was measured on tau-bench (bench/taubench.py), against planted fabrications:

| operands drawn from | flags explained | planted fabrications "explained" by coincidence |
|---|---:|---:|
| Supported values the Output states (experiment, any Kind) | 51.5% | 2.0% |
| **as built: Supported values the Output states, same Kind** | **44.8%** | **0.5%** |
| any Source value (pairs only) | 77.0% | 61.7% |

(The experiment sampled 35% of runs. The as-built row covers all 22,179 turns, `bench/taubench.py`.)

A search over the Sources explains most fabrications too, because a few hundred prices produce a sum or difference near almost any value. Restricted to the Output, a coincidence is rare, and the operands are values the reader can see next to the flag. That also exposes a wrong-operand total such as `282 − 177` where the old itinerary cost `177 + 146`.

Decisions:
- A Derivation never changes a verdict. The Claim stays Unsupported (ADR-0005), and `ok` is unchanged.
- The operand Claims are of the same Kind as the target. A multiplier is a Supported whole number from 2 to 9 ("2 passengers").
- The operations are a difference of two operands, a sum of 2 to 5, and one operand times a multiplier. The search order is fixed and shared by both ports: differences, then sums by size, then products, each over operands in ascending order. Sums of 4 or 5 are tried only for up to 16 operands, and sums of 3 only for up to 60, which bounds the cost.
- Date arithmetic ("move it by one day") is not covered.
- **Amended 2026-09-27: ratios.** A percentage stated to at least one decimal is also searched as a ÷ b × 100 or (a − b) ÷ b × 100, over two Supported numbers, or two Supported amounts in one currency. The result is rounded half-up to the Claim's own decimals, and the search runs last, on the same work budget.

  Measured before building (`bench/ratio_experiment.py`):
  - The loose version, with any percentage and also means, "explained" 2.3% of planted fabrications, and was rejected.
  - The strict one explained 8% of the flags on correct FinQA/TAT-QA answers, and 0.03% of fabrications.

  Built, it moved RAGBench table QA from 61.9% to 60.2% of correct answers flagged, and left τ²-bench unchanged (Derivations on 41.9% of flags, 1.0% of caught fabrications explained by coincidence). A whole percentage ("35%") is never searched, because too many ratios round to it.

Considered, and rejected:
- **Operands from the Sources.** See the table above.
- **Accepting derived values as Supported.** ADR-0005 rules this out: 10% of the audited derivations were wrong.
- **"Rounded from a Source number"** (`13.5M` from `13,486,872`, which is how Claude reports tool output in coding sessions). Measured with 2+ significant digits:
  - It explains 8.8% of τ-bench's unexplained numeric flags and 1.9% of RAGTruth train's.
  - It "explains" 2.0% and 0.8% of planted fabrications by coincidence.

  Too little signal for a new concept.
