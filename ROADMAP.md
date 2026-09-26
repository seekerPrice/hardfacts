# Roadmap: the known gaps, with their numbers

These are measured gaps, not wishes. Each one says where the evidence is. A fix is welcome if it comes with a failing test first, keeps `tools/verify.sh` green, and reports what it changes on the benchmarks. Several past fixes that looked safe were caught by a hostile review, so the numbers matter more than the idea.

## Answers that are calculations

- **Ratios and percentage changes.** On RAGBench's FinQA and TAT-QA, 61.8% of correct answers are flagged, because "the rate of return is 37.9%" is (137.9 − 100) / 100, and Derivations only cover differences, sums and small multiples ([results](docs/reviews/2026-09-27-ragbench-results.md)). Two versions of a ratio search were measured in `bench/ratio_experiment.py`:

  | variant | flags explained | fabrications "explained" by coincidence |
  |---|---:|---:|
  | loose | 30% | 2.3% |
  | strict: percentages only, with a stated decimal | 8% | 0.03% |

  The strict version is now built ([ADR-0007](docs/adr/0007-derivations-come-from-the-output.md), amended): table QA moved from 61.9% to 60.2% of correct answers flagged. Most table answers still combine more than two values or state whole percentages. That is the open question, and operands restricted to the sentence the value appears in are one idea.
- **Date arithmetic.** "Your trip is 5 days", computed from two dates, is flagged, and no Derivation shows it. It was measured and deprioritised (`bench/date_diff_experiment.py`): across every τ-bench and τ²-bench reply, only 10 flagged numbers are day counts, and none is the difference between two dates in the same reply. Real data first; a reply set where this is common would change the answer.
- **Circular Derivations.** When an agent computes a remainder *from* an invented total, the total gets "explained" by the remainder ([τ²-bench results](docs/reviews/2026-09-26-tau2bench-results.md)). Fixing it needs tool-call provenance, which text alone doesn't carry.

## Values hardfacts doesn't read yet

- **Space-grouped thousands** (`90 973`) and typo'd dates (`March 18. 2021`), found in the RAGBench audit. Space grouping was measured and deprioritised: across all 11,802 RAGBench answers, only 1 has an unsupported number that the grouping would support.
- **Units.** Matching ignores units, so "20cm" supports "20 minutes". Requiring unit agreement was measured and made things worse ([ADR-0006](docs/adr/0006-values-not-context.md)). A narrower rule might not.
- **Names no source mentions.** Since [ADR-0008](docs/adr/0008-names-are-checked-against-their-siblings.md), a name is checked when the sources name something of the same shape (`COVID-12` against `COVID-19`), which lifted RAGBench name recall from 46% to 96%. A name whose shape no source contains still passes, so an invented model number with no sibling isn't caught.

## Found by the whole-library review (round 11), not yet fixed

- **Time zones are ignored.** "3pm MYT" is supported by `2025-10-03T15:00:00Z`, which is 11pm in Malaysia, and "3pm SGT" by "3pm MYT". The fix is to read zone designators into the time Value and compare in UTC only when both sides state a zone. Only 157 of 68,115 τ-bench and τ²-bench agent turns state a time with a zone, almost all repeating the policy's own "EST".
- **An invented country code passes.** "+65 12-345 6789" is supported by a Malaysian local number "012-345 6789", although the Claim is more specific than its Evidence. When the Evidence has a trunk 0 and no country code, a Claim's country code should need support elsewhere in the Sources.
- **Last-digit references match any number.** "card ending in 1234" is supported by the customer's phone number, or by an order ID with those last digits. The reference should prefer Evidence of the same sort (a card or account ID) when the Sources have one.
- **Weekdays aren't checked.** "Friday, October 3" passes against "Wednesday, October 3". Measured before building (`bench/weekday_experiment.py`): across 68,115 τ-bench and τ²-bench agent turns, only 2 of 10,018 dates come with a weekday, and both are right. Deprioritised until a reply set shows the error.
- **Minor units named by a field.** `{"fee_cents": 50}` doesn't support "50 cents": the Claim is $0.50, and the Source states a bare 50. "My 2 cents" is read as $0.02. (Round 12.)
- **Shorthand after compound units.** `一亿五` and `一百万五` aren't read as 150 million and 1.5 million, and `3万5` splits into two numbers. (Round 12; still open after round 11's `一万五` fix.)

## Languages

- **Bahasa Melayu and 中文** rules have not had a full native-speaker review. Realistic support replies in BM, 中文 and Manglish, added as tests, are the most useful contribution anyone can make here.

## Packaging

- **PyPI and npm** packages will be published when the repository reaches 100 stars. Until then: `pip install "git+https://github.com/seekerPrice/hardfacts"`.
