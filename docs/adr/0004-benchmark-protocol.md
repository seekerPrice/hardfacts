# ADR-0004: Rules are tuned on RAGTruth train; test is reported, never tuned on

Every extraction and matching rule is developed against the RAGTruth train split (15,090 responses). The test split (2,700 responses) is only used to produce the published numbers, and every run is recorded with its commit hash. That keeps the headline numbers honest: tuning on test would inflate precision in exactly the way this project exists to catch. If test numbers are disappointing, the fix is made against train failures and test is re-run. The protocol stays the same.
