"""Measure, before building: a check for digits changed inside names ("COVID-19" → "COVID-12").

    uv run --with pyarrow python bench/name_experiment.py

Short letter-and-digit mixes are read as names, not values, so a changed digit inside one is never
checked. On RAGBench 40–65% of fabrications planted into names were caught, against 96–100% for
values (docs/reviews/2026-09-27-ragbench-results.md). The candidate rule flags a name in the Output
when the Sources don't contain it but do contain a name of the same shape (digit runs as "#"):
"COVID-12" against "COVID-19", "H2N1" against "H1N1", "Schedule 16G" against "13G". A name whose
shape the Sources never mention is left alone.

It reports:
  caught       fabrications planted into names that the rule flags (RAGBench, same planting as ragbench.py)
  new flags    adherent RAGBench responses (all 12 subsets) that the rule would newly flag
  on RAGTruth  clean RAGTruth test responses it would newly flag
"""

from __future__ import annotations

import json
import random
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fault_injection import DIGITS, META, fabricate  # noqa: E402
from ragbench import HERE, rows  # noqa: E402

from hardfacts import check  # noqa: E402

NAME = re.compile(r"(?<![\w.-])(?=[\w-]*[A-Za-z])(?=[\w-]*\d)[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*(?![\w-]|\.\d)")
"""A token mixing letters and digits: COVID-19, CD8, IL-4, H5N1, 13G, 4WD, KATNAL1."""
CURRENCY = re.compile(r"(?i)^(?:rm|rmb|usd|us|sgd|eur|gbp|jpy|cny|inr|idr|thb|php|vnd|aud|cad|hkd|nzd|rp|rs)\d")
"""An amount written against its currency code ("RMB105") is money, which the money recogniser checks."""


def shape(token: str) -> str:
    return re.sub(r"\d+", "#", token.lower())


def names(text: str) -> list[re.Match]:
    return [m for m in NAME.finditer(text) if not CURRENCY.match(m.group())]


def unclaimed(output: str, sources: str) -> list[tuple[int, int]]:
    """Spans hardfacts already checks as values; the name rule only covers what it doesn't."""
    return [c.span for c in check(output, [sources]).claims]


def changed_names(output: str, sources: str) -> list[tuple[str, str]]:
    shapes: dict[str, set[str]] = {}
    for m in names(sources):
        shapes.setdefault(shape(m.group()), set()).add(m.group().lower())
    lowered = sources.lower()
    hits = []
    claimed = unclaimed(output, sources)
    for m in names(output):
        if any(a < m.end() and m.start() < b for a, b in claimed):
            continue
        whole = m.group().lower()
        seen = shapes.get(shape(whole))
        if seen and whole not in seen and whole not in lowered:
            hits.append((m.group(), sorted(seen)[0]))
    return hits


def main() -> int:
    rng = random.Random(0)
    planted = Counter()
    caught = Counter()
    adherent = Counter()
    flagged = Counter()
    examples: list[str] = []
    for r in rows(HERE / "data" / "ragbench"):
        if not r["adherence_score"]:
            continue
        output, sources = r["response"] or "", [d for d in r["documents"] if d]
        prompt = "\n".join(sources)
        adherent[r["subset"]] += 1
        hits = changed_names(output, prompt)
        if hits:
            flagged[r["subset"]] += 1
            if len(examples) < 25:
                examples.append(f"{r['subset']}: {hits[:3]}")
        meta = [x.span() for x in META.finditer(output)]
        eligible = [m for m in DIGITS.finditer(output) if re.search(rf"(?<!\d){m.group()}(?!\d)", prompt)
                    and not any(a <= m.start() < b for a, b in meta)]
        if not eligible:
            continue
        m = rng.choice(eligible)
        new = fabricate(m.group(), prompt, rng)
        if new is None:
            continue
        in_name = bool(re.search(r"[A-Za-z]-?$", output[max(0, m.start() - 2):m.start()]) or re.match(r"[A-Za-z]", output[m.end():m.end() + 1]))
        if not in_name:
            continue
        mutated = output[:m.start()] + new + output[m.end():]
        planted[r["subset"]] += 1
        caught[r["subset"]] += any(new in h[0] for h in changed_names(mutated, prompt))
    ragtruth_clean = ragtruth_flagged = 0
    data = HERE / "data"
    src = {json.loads(line)["source_id"]: json.loads(line) for line in (data / "source_info.jsonl").read_text(encoding="utf-8").splitlines()}
    for line in (data / "response.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["split"] != "test" or r["labels"]:
            continue
        ragtruth_clean += 1
        ragtruth_flagged += bool(changed_names(r["response"], src[r["source_id"]]["prompt"]))
    result = {
        "name_plants": sum(planted.values()), "caught": sum(caught.values()),
        "caught_share": round(sum(caught.values()) / max(1, sum(planted.values())), 4),
        "adherent_responses": sum(adherent.values()), "newly_flagged": sum(flagged.values()),
        "newly_flagged_share": round(sum(flagged.values()) / sum(adherent.values()), 4),
        "newly_flagged_by_subset": dict(flagged),
        "ragtruth_clean_test": ragtruth_clean, "ragtruth_newly_flagged": ragtruth_flagged,
        "examples": examples,
    }
    print(json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
