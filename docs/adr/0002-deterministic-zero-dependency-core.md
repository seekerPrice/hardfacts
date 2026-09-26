# ADR-0002: The core is deterministic, with zero runtime dependencies

The checker is pure Python standard library. It has no NER model, no embeddings and no LLM call. That gives the three properties a pre-filter needs: it costs nothing to run on every response, it returns the same answer every time (so a flag can be audited and reproduced), and it installs anywhere, from a Lambda to an air-gapped client. An LLM judge belongs in the integration layer as the thing flagged Outputs are routed to, not inside the check.

Considered and rejected: spaCy or another NER for entity extraction. It improves recall on names but adds a model download and weakens determinism, and names are not Hard facts in this project's language anyway.
