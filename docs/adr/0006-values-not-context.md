# ADR-0006: Match values, not the words around them

A bare quantity Claim is Supported by any Source number with the same Value, whatever noun follows it. So `5 people` is supported by `5 minutes`. That is how Binding errors slip through, and it was measured before being accepted. On RAGTruth train, adding unit agreement (the word after a number must match the word after the Evidence) raised recall on swapped numbers from 18.6% to 30.2%. It cost span precision 0.718 → 0.596 and more than doubled the share of clean responses flagged (2.1% → 5.3%). These are the figures re-measured after the swap metric was corrected; the originally recorded 39% → 48% counted fragment swaps. Precision falls because Sources say `6 victims` where outputs say `6 people`. Under ADR-0003 that trade is refused.

Also measured and rejected: letting a time Claim (`10 PM`) be supported by a bare number equal to its hour (`open until 10`). Precision fell 0.710 → 0.704 and fabricated-time recall fell 0.97 → 0.85.

Binding needs real context (a parse, or a model), which puts it out of scope for the deterministic core (ADR-0002).

Also measured and rejected: reading a hedged round number as a range (`over 60` → 60–70, `about $2 billion` → 1.5–2.5 billion). Span precision barely moved (0.710 → 0.712), but hard-fact recall fell 0.501 → 0.490 (Summary 0.560 → 0.528). A range catches unrelated numbers by coincidence: `over 15 years` was "supported" by a 19-year-old's age, and `over 100 sites` by a 175-foot statue.
