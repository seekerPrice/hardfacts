# Roadmap: the known gaps, with their numbers

These are measured gaps, not wishes. Each one says where the evidence is. A fix is welcome if it comes with a failing test first, keeps `tools/verify.sh` green, and reports what it changes on the benchmarks. Several past fixes that looked safe were caught by a hostile review, so the numbers matter more than the idea.

## Answers that are calculations

- **Ratios and percentage changes.** On RAGBench's FinQA and TAT-QA, 61.8% of correct answers are flagged, because "the rate of return is 37.9%" is (137.9 − 100) / 100, and Derivations only cover differences, sums and small multiples ([results](docs/reviews/2026-09-27-ragbench-results.md)). Two versions of a ratio search were measured in `bench/ratio_experiment.py`:

  | variant | flags explained | fabrications "explained" by coincidence |
  |---|---:|---:|
  | loose | 30% | 2.3% |
  | strict: percentages only, with a stated decimal | 8% | 0.03% |

  Neither was built. Something in between, such as operands restricted to the sentence the value appears in, is the open question.
- **Date arithmetic.** "Your trip is 5 days", computed from two dates, is flagged, and no Derivation shows it.
- **Circular Derivations.** When an agent computes a remainder *from* an invented total, the total gets "explained" by the remainder ([τ²-bench results](docs/reviews/2026-09-26-tau2bench-results.md)). Fixing it needs tool-call provenance, which text alone doesn't carry.

## Values hardfacts doesn't read yet

- **Space-grouped thousands** (`90 973`) and typo'd dates (`March 18. 2021`), found in the RAGBench audit.
- **Units.** Matching ignores units, so "20cm" supports "20 minutes". Requiring unit agreement was measured and made things worse ([ADR-0006](docs/adr/0006-values-not-context.md)). A narrower rule might not.
- **Names no source mentions.** Since [ADR-0008](docs/adr/0008-names-are-checked-against-their-siblings.md), a name is checked when the sources name something of the same shape (`COVID-12` against `COVID-19`), which lifted RAGBench name recall from 46% to 96%. A name whose shape no source contains still passes, so an invented model number with no sibling isn't caught.

## Languages

- **Bahasa Melayu and 中文** rules have not had a full native-speaker review. Realistic support replies in BM, 中文 and Manglish, added as tests, are the most useful contribution anyone can make here.

## Packaging

- **PyPI and npm** packages will be published when the repository reaches 100 stars. Until then: `pip install "git+https://github.com/seekerPrice/hardfacts"`.
