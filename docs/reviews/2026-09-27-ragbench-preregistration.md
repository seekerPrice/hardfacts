# Pre-registration: hardfacts on RAGBench

Written and committed before any RAGBench response was checked. RAGBench is the first test on data hardfacts was never developed near. It covers 12 RAG datasets (medicine, law, finance, manuals, the open web), with different generators and a different annotator. It also scores RAGAS, TruLens and a GPT-3.5 judge on the same responses, so hardfacts can be compared with the LLM-based checkers people actually deploy.

## What is fixed in advance

- **Checker:** the commit named in the "Frozen at" line. No rule changes between that commit and the scored run.
- **Data:** RAGBench (Galileo, CC BY 4.0), test splits of all 12 subsets, at dataset revision `97808f3`, fetched by `bench/fetch_ragbench.sh`. That is 11,802 responses, of which 1,677 (14.2%) are labelled not adherent. The only things inspected were the schema and the per-subset label counts. No check was run.
- **Labels:** GPT-4 annotations (response-level `adherence_score` and unsupported sentence keys), **not human labels**. The RAGBench paper reports agreement with human judgement, but everything below measures agreement with a GPT-4 annotator.
- **Method:** `bench/ragbench.py`. The Output is `response` and the Sources are `documents`. A response is flagged when `report.unexplained` is non-empty. Fault injection follows `bench/fault_injection.py`: on each adherent response, one digit of one number the documents state is changed. The seed is 0.
- **Baselines:** `ragas_faithfulness`, `trulens_groundedness` and `gpt3_adherence` are the dataset's own columns. Each flags its lowest-scoring responses, as many as hardfacts flags among the rows where it has a score, and precision is compared at that equal count.

## Predictions

| metric | prediction | fails if |
|---|---:|---|
| planted fabrications caught | ≥ 93% | < 88% |
| adherent responses flagged: the ten non-numeric subsets | ≤ 10% | > 20% |
| adherent responses flagged: FinQA + TAT-QA | ≤ 40% | > 60% |
| response precision (flagged → not adherent): the ten non-numeric subsets (base rate 22%) | ≥ 35% | < 25% |
| response precision: FinQA + TAT-QA (base rate 5.5%) | ≥ 10% | < 7% |
| hardfacts vs RAGAS faithfulness at equal flag counts, non-numeric ten | within 10 points of RAGAS, or above it | more than 10 points below |

**Why FinQA and TAT-QA are predicted badly.** Their answers compute ratios, percentage changes and averages from tables. Derivations cover only differences, sums of 2–5 values and products by a small multiplier (ADR-0007). So a correct "the rate of return is 37.9%" is flagged as unexplained. That is a known limit, not something tuned away before this run.

**Confidence.** Fabrication recall: high, since it has held on every dataset so far. Adherent flag rates and precision: moderate. The comparison with RAGAS: low. An LLM judge also catches prose-level unfaithfulness, which hardfacts can't see, so hardfacts may lose on precision while costing nothing to run. Recall of non-adherent responses is reported without a prediction. Most unfaithfulness in RAG is prose, so it is expected to be low.

## What happens after

The numbers are reported as they come out, including misses. Checker errors may then be fixed, and any later run is labelled post-fix.

Frozen at: checker `33b1cef` plus later commits that touch only docs, examples and CI. `git diff 33b1cef HEAD -- src ts/src` is empty except for the MCP server's `TypedDict` import.
