# RAGBench results against the pre-registration

Scored once at `2c41f4e`, the commit that holds the [pre-registration](2026-09-27-ragbench-preregistration.md) ([results](../../bench/results/ragbench-2c41f4e.json)). It covers 11,802 test responses over 12 RAG datasets. The labels are **GPT-4 annotations**, not human ones.

**Two of six predictions failed, both on table arithmetic.** On the other ten datasets, hardfacts is precise and quiet but sees little. It matches RAGAS's precision in aggregate but loses to it on most individual datasets, and it catches about 1 in 9 unfaithful responses.

## Scorecard

| prediction | predicted | result | verdict |
|---|---:|---:|---|
| planted fabrications caught | ≥ 93% | **96.0%** (numeric 99.3%, other ten 89.2%) | pass |
| adherent responses flagged, other ten | ≤ 10% | **4.6%** | pass |
| adherent responses flagged, FinQA + TAT-QA | ≤ 40% | **61.8%** (FinQA 82.5%) | **fail** |
| response precision, other ten (base rate 22%) | ≥ 35% | **40.2%** | pass |
| response precision, FinQA + TAT-QA (base rate 5.5%) | ≥ 10% | **6.25%** | **fail** |
| vs RAGAS at equal flag counts, other ten | within 10 points | **41.0% vs 39.0%** | pass |

## The comparison with LLM-based checkers, read carefully

At equal flag counts on the ten non-numeric datasets, hardfacts' flagged responses were non-adherent 41.0% of the time. The figures for the others were RAGAS faithfulness 39.0%, a GPT-3.5 adherence judge 27.1%, and TruLens groundedness 14.8%.

That aggregate flatters hardfacts. **Per dataset, RAGAS is more precise on 6 of the 10**: CovidQA, CUAD, HAGRID, HotpotQA, MS MARCO and PubMedQA. The two tie on EManual and DelucionQA. hardfacts wins clearly only on ExpertQA (87% vs 73%) and TechQA (64% vs 45%). Those two account for many of its flags, so they carry the aggregate. Several per-dataset comparisons rest on 1 to 14 flags, so read them as direction, not measurement.

The honest summary: **a free, deterministic check is in the same precision range as RAGAS, better than TruLens and a GPT-3.5 judge, and it sees far less.** Its recall of non-adherent responses on the ten datasets is 10.8%, because most unfaithful RAG answers are wrong in prose, not in a number. That is the pre-filter role the README already claims, not a replacement for a judge.

| dataset | responses | not adherent | hardfacts flags | precision | recall | adherent flagged | fabrications caught | RAGAS precision, same count |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| CovidQA | 246 | 39 | 8 | 0.50 | 0.10 | 1.9% | **51.9%** | 0.57 |
| CUAD | 510 | 38 | 14 | 0.00 | 0.00 | 3.0% | 82.0% | 0.46 |
| DelucionQA | 184 | 12 | 1 | 0.00 | 0.00 | 0.6% | 91.8% | 0.00 |
| EManual | 132 | 14 | 1 | 1.00 | 0.07 | 0.0% | 100% | 1.00 |
| ExpertQA | 203 | 108 | 30 | **0.87** | 0.24 | 4.2% | 85.7% | 0.73 |
| FinQA | 2,294 | 196 | 1,875 | 0.08 | 0.74 | **82.5%** | 99.3% | 0.09 |
| HAGRID | 1,318 | 211 | 183 | 0.29 | 0.25 | 11.7% | 96.0% | 0.36 |
| HotpotQA | 390 | 32 | 4 | 0.25 | 0.03 | 0.8% | 94.7% | 0.75 |
| MS MARCO | 423 | 55 | 5 | 0.20 | 0.02 | 1.1% | 99.2% | 0.60 |
| PubMedQA | 2,450 | 725 | 54 | 0.35 | 0.03 | 2.0% | 86.6% | 0.44 |
| TAT-QA | 3,338 | 116 | 1,631 | 0.05 | 0.64 | 48.3% | 99.2% | 0.05 |
| TechQA | 314 | 131 | 66 | **0.64** | 0.32 | 13.1% | 77.3% | 0.45 |

## Why table QA fails

FinQA and TAT-QA answers compute ratios, percentage changes and averages from financial tables. For example, "the rate of return is 37.9%", from 137.90 and 100.00. Derivations cover differences, sums of 2–5 values and small multiples only (ADR-0007), so a correct ratio is unexplained and flagged. 82.5% of adherent FinQA answers are flagged. This was predicted as a weakness and came out worse than predicted.

The data also shows the other side. Fabrications planted in those same answers are caught 99.3% of the time, and 74% of the non-adherent FinQA answers are flagged. The checker is doing its job, which is to flag every number no source states. Its job is the wrong one for a product whose answers are supposed to be calculations.

## What needs a closer look before anything is changed

- **CovidQA fabrication recall is 51.9%.** Investigated after the score: every miss is a digit changed inside a **name**. Examples are `COVID-19` → `COVID-12`, `H1N1` → `H2N1`, `CD8` → `CD6`, `IL-4` → `IL-9` and `KATNAL1` → `KATNAL2`. hardfacts reads short letter-and-digit mixes as names, not values. That rule was measured on RAGTruth, where it keeps `COVID-19` and `B12` from flooding the flags. The planting harness doesn't know about it.

  Split after the fact, by whether the changed digit touches a letter:

  | plants | numeric subsets | other ten |
  |---|---:|---:|
  | into a value | **99.8%** of 4,642 | **96.4%** of 1,979 |
  | into a name | 65.4% of 78 | 40.4% of 292 |

  This split was done after scoring, so the pre-registered number stays 96.0%. It was a real gap: "COVID-12" or a wrong gene name went uncaught, and biomedical RAG is full of such names. Since fixed by ADR-0008 (name plants caught: 46% → 96%).
- **Only 30% of the flags on the ten datasets fall in a sentence GPT-4 marked unsupported**, while 40% of flagged responses are non-adherent. So a blind double audit ([files](../../bench/audit/ragbench/)) took 60 flags, seeded, one per response, from the 219 adherent responses in the ten datasets that hardfacts flagged. The two auditors agreed on 59 of 60 (κ 0.97).

  | verdict | flags |
  |---|---:|
  | invented: the documents never state it, and the GPT-4 annotator passed it | 16 |
  | derived: computed from the documents (all 5 correctly) | 5 |
  | **not a claim** | **30** |
  | missed support: the documents state it in a form hardfacts didn't read | 9 |

  **65% of these flags were checker errors**, unlike RAGTruth, where auditing the same gap found mostly real inventions. **24 of the 30 "not a claim" verdicts are citation markers**: `…killed [10]`, `[1, 2, 3, 4, 5]`, `[1-6]`. RAGTruth's responses cite as "passage 2" and τ-bench's don't cite at all, so bracketed markers were never seen before. The rest are a list number, a name ("Millennium Development Goal 4", "sVEGFR-1") and bibliography years.

  The missed supports are formats hardfacts doesn't read yet: a Lancet-style decimal (`37·8°C`, since fixed), space-grouped thousands (`90 973`), a typo'd date (`March 18. 2021`), versions written `V9.1/V9.5`, and a residue in `Asp76Asn`.

  The 16 inventions are the other side: numbers the GPT-4 annotator passed as supported, and the reason 40% response precision coexists with 30% sentence overlap.

## Post-fix (not out-of-sample)

The audit's main finding was fixed test-first in both ports: bracketed citation markers are no longer claims. A hostile review of the first version found it exempted any bracketed list ("the scores were [7, 8, 9]" passed against "7, 8 and 3"). The fix was narrowed so a bare marker counts only where it closes a clause and no value-introducing word leads into it. Neither version changes any of the ~40,000 RAGTruth and τ-bench outputs. Re-scored at the fixed checker ([results](../../bench/results/)):

| other ten datasets | held-out | post-fix |
|---|---:|---:|
| responses flagged | 366 | 256 |
| response precision | 40.2% | **48.8%** |
| adherent responses flagged | 4.6% | **2.7%** |
| flags in a GPT-4-unsupported sentence | 30.0% | 38.3% |
| recall of non-adherent responses | 10.8% | 9.2% |
| hardfacts vs RAGAS at equal flag counts | 41.0% vs 39.0% | **50.2% vs 39.0%** |
| planted fabrications caught | 89.2% | 88.0% (plants into "[10]" now land in an exempt marker) |

FinQA and TAT-QA are unchanged. Because the citation problem was found on this data, the post-fix precision is a bug-fix measurement, not a second held-out result.

### Post-fix 2: names (ADR-0008)

Fabrications planted into names (`COVID-19` → `COVID-12`) were the biggest recall gap, so names are now checked against same-shaped names in the documents ([ADR-0008](../adr/0008-names-are-checked-against-their-siblings.md), measured first in `bench/name_experiment.py`). On the other ten datasets, fabrications caught rose from 88.0% to **95.4%**. Precision is 49.6%, recall 9.4%, and 2.7% of adherent responses are flagged. At equal flag counts the figures are hardfacts 51.2% and RAGAS 39.3%. A hostile review of the first version found a quadratic slowdown and a hyphen-merging false "Supported" (`X1-2` matching `X12`), and both were fixed before this run.
