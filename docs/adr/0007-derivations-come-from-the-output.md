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
- **Ratios were built and then withdrawn (2026-09-27).** A search for a ÷ b × 100 and (a − b) ÷ b × 100, for a percentage stated to a decimal, was measured first (`bench/ratio_experiment.py --strict`: 8% of flags on correct table answers explained, 0.03% of planted fabrications) and built. Two hostile reviews then took it apart:
  - Round 15 showed chance matches grow with the number of values in a reply (42% of random percentages "explained" at 20 numbers), so the search was cut to the three nearest values.
  - Round 16 showed a worse problem that no bound fixes. The commonest percentage error, a change taken on the wrong base ("from RM120 to RM150, an increase of 20.0%", when it is 25%), got a Derivation, `(RM150 − RM120) ÷ RM150`, and left `unexplained`, which silences the Stop hook and the retry loop. For a difference or a sum, a Derivation shows which values were combined. For a percentage, the error lies in the choice of base, so the working hides it.

  The benefit was small (table QA 61.9% → 61.3% of correct answers flagged), and the harm fell on the exact error it would be trusted to catch. A percentage is never searched as a ratio.

Considered, and rejected:
- **Operands from the Sources.** See the table above.
- **Accepting derived values as Supported.** ADR-0005 rules this out: 10% of the audited derivations were wrong.
- **"Rounded from a Source number"** (`13.5M` from `13,486,872`, which is how Claude reports tool output in coding sessions). Measured with 2+ significant digits:
  - It explains 8.8% of τ-bench's unexplained numeric flags and 1.9% of RAGTruth train's.
  - It "explains" 2.0% and 0.8% of planted fabrications by coincidence.

  Too little signal for a new concept.
