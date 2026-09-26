# ADR-0005: Derived values are Unsupported by default

A value the model computed from the Sources is not in any Source, so hardfacts reports it as Unsupported. That covers a unit conversion (`400°F` → `(200°C)`), a sum, a difference and a count. This was measured, not assumed. On RAGTruth train, treating °F↔°C conversions (rounded the way people round) as Supported removed 77 QA false positives but lost 39 hard-fact hallucinations. The annotators label added conversions as baseless information, and so does any strict reader. A derived value might be right, but it has no provenance, and provenance is the only thing this tool claims to check.

Considered: tolerance-based conversion matching (implemented, measured, reverted). If callers want conversions or arithmetic accepted, that becomes an explicit opt-in, never a default.
