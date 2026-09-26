# Sample client reports

These are what `hardfacts report` produces, rebuilt from the benchmark data by `build.py`:

| Report | What was checked | Responses flagged | …with a value that isn't arithmetic on its own numbers |
|---|---|---:|---:|
| [`support-agents.html`](support-agents.html) | every reply GPT-4o wrote as a retail and an airline support agent in [τ-bench](https://github.com/sierra-research/tau-bench)'s published runs (MIT), checked against the tool definitions, policy, user turns and tool results it had seen | 220 / 4,937 (4.5%) | 113 |
| [`business-listings.html`](business-listings.html) | 900 business write-ups by six LLMs from Yelp-style JSON records (RAGTruth test split, Data2txt; MIT, ParticleMedia) | 101 / 900 (11.2%) | 101 |

```bash
uv run hardfacts report transcripts.jsonl --html report.html --json report.json --fail-over 0.05
```

Each input line is `{"id": ..., "output": "<the model's reply>", "sources": [<what it was given>, ...]}`. Run it on a client's transcripts, then walk them through the examples.

In the support-agent report, 152 of the 309 unsupported values are arithmetic on values the reply itself states: price differences, fare totals. Each is shown with its working (ADR-0007), and those need a different conversation with the client than invented values do. In the blind audit of τ-bench flags, 11 of 115 such computations were wrong: a fare difference taken against one leg of a two-leg trip, 12 T-shirt options "available" when 10 are, a $35.94 refund stated as $235.94.
