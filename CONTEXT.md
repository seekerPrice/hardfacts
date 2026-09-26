# hardfacts

Checks that every hard fact an LLM writes can be traced to something the model was given. It checks where each value came from, not whether the prose is true.

## Language

### Inputs

**Output**:
The LLM-generated text under check.
_Avoid_: response, answer, completion (fine in prose, but not as the term)

**Source**:
One piece of material the model was given when it wrote the Output: a retrieved passage, a tool result, a JSON record or the prompt itself. A check takes one Output and any number of Sources.
_Avoid_: context, document, reference

### Facts

**Hard fact**:
A span of text whose meaning is a single checkable value: a quantity, percent, money amount, date, time, phone number, email address, URL or identifier.
_Avoid_: entity (too broad; names and places are not hard facts), number (too narrow)

**Kind**:
The category of a Hard fact, which decides how its Value is read and compared.

**Value**:
The canonical meaning of a Hard fact, independent of how it was written. `9 PM`, `21:00` and `21:0` share one Value.
_Avoid_: normalised form

**Surface form**:
The exact characters a Hard fact was written with.

**Specificity**:
How much of a Value is pinned down. `February 7` is less specific than `February 7, 1945`. A Claim may be less specific than its Evidence, but never more.

**Name**:
A token mixing letters and digits that names something rather than stating a value: `COVID-19`, `CD8`, `H1N1`, `Schedule 13G`. It is a Claim only when a Source contains a name of the same **shape** (digit runs as `#`: `COVID-12` is shaped like `COVID-19`), and it is Supported only by the same name.
_Avoid_: identifier (an identifier is itself the value, such as an order ID; a name is checked only against its siblings)

**Exempt span**:
Text that looks like a Hard fact but asserts nothing about the world, such as a list marker (`4.`) or a statement about the Output itself (`summary in 88 words`).

### Verdicts

**Claim**:
A Hard fact found in the Output.

**Evidence**:
A Hard fact found in a Source, located by Source index and character span.

**Supported**:
A Claim is Supported when at least one piece of Evidence has a compatible Value. Supported Claims carry their Evidence.

**Unsupported**:
A Claim with no compatible Evidence in any Source. This is the only thing hardfacts flags.
_Avoid_: hallucination (a hallucination is a judgement about truth; an Unsupported Claim is a missing provenance link)

**Derivation**:
Arithmetic that produces an Unsupported Claim's Value from other Claims in the same Output that are Supported: `$6.32` is `$101.12 − $94.80`. A Derivation explains a flag; it never makes the Claim Supported, and it shows its operands so a reader can see a sum built from the wrong values.
_Avoid_: verified, correct (a Derivation says how a value could have been computed, not that it should have been)

**Binding error**:
A Supported value attached to the wrong subject: the Source says Gordon's net worth is $2.1 billion, and the Output gives that figure to Andrew. hardfacts does not detect these.

**Report**:
The result of one check: every Claim with its verdict and any Evidence.

### Benchmark

**Gold span**:
A character span that human annotators labelled as hallucinated in the benchmark data.

**Hard-fact hallucination**:
A Gold span that contains at least one Hard fact. This is the population hardfacts can be expected to find.

**Flag**:
An Unsupported Claim counted during evaluation. A Flag is a true positive when it overlaps a Gold span.
