"""Measure, before building: would ratio, percentage-change and mean Derivations help?

    uv run --with pyarrow python bench/ratio_experiment.py [--strict]

RAGBench's FinQA and TAT-QA answers compute ratios and percentage changes, which ADR-0007's search
(differences, sums, small multiples) can't express, so 61.8% of adherent answers are flagged. This
prototype searches the Output's own Supported numbers (any Kind: amounts divide into percentages)
for a/b, a/b×100, (a−b)/b×100 and the mean of 2–3 values, rounded to the Claim's own decimals.

It reports the two numbers ADR-0007 weighed:
  explained    the share of unexplained flags on adherent FinQA/TAT-QA answers that it explains
  coincidence  the share of planted fabrications on RAGBench that it would "explain"
A Derivation never changes a verdict, but one on a fabrication tells the reviewer it's arithmetic.
"""

from __future__ import annotations

import itertools
import json
import random
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fault_injection import DIGITS, META, fabricate  # noqa: E402
from ragbench import HERE, NUMERIC, rows  # noqa: E402

from hardfacts import check  # noqa: E402

OPERANDS = 12  # the search looks at the first few supported numbers only, as ADR-0007's budget does


def number(value) -> Decimal | None:
    v = value[-1] if isinstance(value, tuple) else value
    return v if isinstance(v, Decimal) else None


def decimals(text: str) -> int:
    m = re.search(r"\d(?:[.,]\d{3})*\.(\d+)", text)
    return len(m.group(1)) if m else 0


STRICT = "--strict" in sys.argv
"""--strict: percentages and percentage changes only, and only for a Claim that states a decimal."""


def explains(target: Decimal, places: int, operands: list[Decimal]) -> str | None:
    if STRICT and places == 0:
        return None
    q = Decimal(1).scaleb(-places)

    def hit(x: Decimal) -> bool:
        try:
            return x.quantize(q) == target or (-x).quantize(q) == target
        except InvalidOperation:
            return False
    ops = [o for o in operands if o != 0][:OPERANDS]
    for a, b in itertools.permutations(ops, 2):
        if not STRICT and hit(a / b):
            return "ratio"
        if hit(a / b * 100):
            return "percent"
        if hit((a - b) / b * 100):
            return "percent change"
    for k in (() if STRICT else (2, 3)):
        for combo in itertools.combinations(ops, k):
            if hit(sum(combo) / k):
                return "mean"
    return None


def candidates(report):
    supported = [n for c in report.claims if c.supported and c.kind in ("quantity", "money", "percent")
                 and (n := number(c.value)) is not None]
    for c in report.unexplained:
        n = number(c.value)
        if n is not None:
            yield c, n, supported


def main() -> int:
    explained = total = 0
    kinds: dict[str, int] = {}
    rng = random.Random(0)
    planted = coincidences = 0
    for r in rows(HERE / "data" / "ragbench"):
        output, sources = r["response"] or "", [d for d in r["documents"] if d]
        if r["subset"] in NUMERIC and r["adherence_score"]:
            for c, n, supported in candidates(check(output, sources)):
                total += 1
                how = explains(n, decimals(c.text), supported)
                if how:
                    explained += 1
                    kinds[how] = kinds.get(how, 0) + 1
        if r["adherence_score"]:  # coincidences on planted fabrications, same planting as ragbench.py
            prompt = "\n".join(sources)
            meta = [x.span() for x in META.finditer(output)]
            eligible = [m for m in DIGITS.finditer(output) if re.search(rf"(?<!\d){m.group()}(?!\d)", prompt)
                        and not any(a <= m.start() < b for a, b in meta)]
            if not eligible:
                continue
            m = rng.choice(eligible)
            new = fabricate(m.group(), prompt, rng)
            if new is None:
                continue
            mutated = output[:m.start()] + new + output[m.end():]
            span = (m.start(), m.start() + len(new))
            for c, n, supported in candidates(check(mutated, sources)):
                if c.span[0] < span[1] and c.span[1] > span[0]:
                    planted += 1
                    coincidences += explains(n, decimals(c.text), supported) is not None
    result = {"flags_on_adherent_table_answers": total, "explained": explained,
              "explained_share": round(explained / total, 4) if total else None, "by_operation": kinds,
              "planted_fabrications_unexplained_before": planted,
              "given_a_new_derivation_by_coincidence": coincidences,
              "coincidence_share": round(coincidences / planted, 4) if planted else None}
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
