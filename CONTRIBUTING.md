# Contributing

The useful contributions are the ones [ROADMAP.md](ROADMAP.md) lists, and realistic replies in Bahasa Melayu, 中文 or Manglish added as tests. A new rule is easy to write, and most new rules break something the tests don't show. Each step below exists because skipping it once let a regression through.

## A change, step by step

1. **Write the failing test first**, at the public seam: `check(output, sources)`. Say in the test name what a user would notice ("a fraction of something after a date word stays a fraction"). Include a case that must stay *unchanged*: a regression is usually a correct answer that starts getting flagged.
2. **Change both ports.** Python (`src/hardfacts/`) is the reference, and TypeScript (`ts/src/`) must produce identical Reports. Regexes differ between engines (`\s`, `\w`, `$`, lookbehind), so mirror them carefully. Offsets are code points in Python and UTF-16 units in TypeScript.
3. **Run every gate:** `tools/verify.sh`. It covers the tests in both languages, the release check, the RAGTruth train gate and three differentials between the ports. It regenerates the shared conformance fixture, so commit `ts/test/fixture.json` with your change.
4. **Run the claim diff:** `uv run python bench/claim_diff.py`. It lists every one of ~40,000 real outputs whose Claims your change adds, drops or flips, and outputs that gain an Unsupported Claim come first. The gates can pass while a rule quietly flags "1/2 cup" as a date, and this is where that shows. Explain every change it lists, or narrow the rule.
5. **Doubt resolves to Supported** ([ADR-0003](docs/adr/0003-precision-over-recall.md)). When a reading is ambiguous, give the Claim both readings or none. A checker that cries wolf gets switched off.

## Benchmarks

- The RAGTruth **test split is scored once per release** ([ADR-0004](docs/adr/0004-benchmark-protocol.md)). Develop against train only.
- A run on new data is **pre-registered**: commit the predictions and fail thresholds before the first score, as `docs/reviews/*-preregistration.md` do.
- A result after a fix found on that data is **post-fix**, and is labelled so wherever it is quoted.
- An experiment that decides whether to build something goes in `bench/*_experiment.py` with its numbers, including the ones that said no.

## Before a pull request

- `tools/verify.sh` passes, and `bench/claim_diff.py` is explained in the PR description.
- `CHANGELOG.md` says what a user would notice.
- If the change settles a trade-off someone will later question, add an ADR in `docs/adr/`.
