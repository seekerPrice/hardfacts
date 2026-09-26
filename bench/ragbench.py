"""hardfacts on RAGBench (Galileo, CC BY 4.0): an out-of-sample test, and a comparison with RAGAS,
TruLens and a GPT-3.5 judge on the same responses.

    bench/fetch_ragbench.sh
    uv run --with pyarrow python bench/ragbench.py --record

Pre-registered in docs/reviews/2026-09-27-ragbench-preregistration.md. RAGBench has 11,802 test
responses over 12 RAG datasets. Each has GPT-4 annotations: a response-level `adherence_score` and
the keys of unsupported response sentences. The Output is `response` and the Sources are
`documents`. A response counts as flagged when `report.unexplained` is non-empty, which excludes
arithmetic on the response's own supported values (ADR-0007).

Each baseline's score column is ranked lowest-first, and it flags as many responses as hardfacts
did among the rows where it has a score. Comparing precision at equal flag counts needs no threshold.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fault_injection import DIGITS, META, fabricate  # noqa: E402
from hardfacts import check  # noqa: E402

HERE = Path(__file__).parent
SUBSETS = ["covidqa", "cuad", "delucionqa", "emanual", "expertqa", "finqa", "hagrid", "hotpotqa", "msmarco",
           "pubmedqa", "tatqa", "techqa"]
BASELINES = ["ragas_faithfulness", "trulens_groundedness", "gpt3_adherence"]
NUMERIC = {"finqa", "tatqa"}


def rows(data: Path):
    import pyarrow.parquet as pq
    cols = ["id", "documents", "response", "response_sentences", "unsupported_response_sentence_keys",
            "adherence_score", *BASELINES]
    for subset in SUBSETS:
        for r in pq.read_table(data / f"{subset}-test.parquet", columns=cols).to_pylist():
            r["subset"] = subset
            yield r


def sentence_spans(response: str, sentences: list[list[str]]) -> list[tuple[str, int, int]]:
    """Where each annotated response sentence sits in the response (searched in order)."""
    spans, at = [], 0
    for key, text in sentences:
        i = response.find(text.strip(), at)
        if i < 0:
            i = response.find(text.strip())
        if i >= 0:
            spans.append((key, i, i + len(text.strip())))
            at = i + len(text.strip())
    return spans


def score(r: dict, rng: random.Random) -> dict:
    output, sources = r["response"] or "", [d for d in r["documents"] if d]
    report = check(output, sources)
    unexplained = report.unexplained
    unsupported_keys = set(r["unsupported_response_sentence_keys"] or [])
    spans = sentence_spans(output, r["response_sentences"] or [])
    in_bad = 0
    for c in unexplained:
        keys = {k for k, a, b in spans if a <= c.span[0] < b}
        in_bad += bool(keys & unsupported_keys)
    out = {"subset": r["subset"], "id": r["id"], "adherent": bool(r["adherence_score"]),
           "flagged": bool(unexplained), "flags": len(unexplained), "flags_in_bad_sentence": in_bad,
           "has_claims": bool(report.claims), **{b: r[b] for b in BASELINES}}
    if r["adherence_score"]:
        prompt = "\n".join(sources)
        meta = [x.span() for x in META.finditer(output)]
        eligible = [m for m in DIGITS.finditer(output) if re.search(rf"(?<!\d){m.group()}(?!\d)", prompt)
                    and not any(a <= m.start() < b for a, b in meta)]
        if eligible:
            m = rng.choice(eligible)
            new = fabricate(m.group(), prompt, rng)
            if new is not None:
                mutated = output[:m.start()] + new + output[m.end():]
                span = (m.start(), m.start() + len(new))
                hit = any(c.span[0] < span[1] and c.span[1] > span[0] for c in check(mutated, sources).unsupported)
                out["planted"], out["caught"] = 1, int(hit)
    return out


def summarise(scored: list[dict]) -> dict:
    def block(rs: list[dict]) -> dict:
        n = len(rs)
        bad = [r for r in rs if not r["adherent"]]
        flagged = [r for r in rs if r["flagged"]]
        tp = sum(1 for r in flagged if not r["adherent"])
        flags = sum(r["flags"] for r in rs)
        planted = sum(r.get("planted", 0) for r in rs)
        adherent = [r for r in rs if r["adherent"]]
        res = {
            "responses": n, "not_adherent": len(bad), "flagged": len(flagged),
            "response_precision": round(tp / len(flagged), 4) if flagged else None,
            "response_recall": round(tp / len(bad), 4) if bad else None,
            "adherent_flagged": round(sum(r["flagged"] for r in adherent) / len(adherent), 4) if adherent else None,
            "flags_in_unsupported_sentence": round(sum(r["flags_in_bad_sentence"] for r in rs) / flags, 4) if flags else None,
            "planted": planted,
            "fabrications_caught": round(sum(r.get("caught", 0) for r in rs) / planted, 4) if planted else None,
            "baselines_at_equal_flags": {},
        }
        for b in BASELINES:
            have = [r for r in rs if r[b] is not None]
            k = sum(r["flagged"] for r in have)
            if not k:
                continue
            ranked = sorted(have, key=lambda r: (r[b], r["id"]))[:k]
            ours = sum(1 for r in have if r["flagged"] and not r["adherent"])
            res["baselines_at_equal_flags"][b] = {
                "flagged": k, "precision": round(sum(1 for r in ranked if not r["adherent"]) / k, 4),
                "hardfacts_precision_same_rows": round(ours / k, 4)}
        return res
    result = {"ALL": block(scored),
              "numeric (finqa, tatqa)": block([r for r in scored if r["subset"] in NUMERIC]),
              "other ten": block([r for r in scored if r["subset"] not in NUMERIC])}
    for s in SUBSETS:
        result[s] = block([r for r in scored if r["subset"] == s])
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=HERE / "data" / "ragbench")
    ap.add_argument("--record", action="store_true")
    ap.add_argument("--label", default="")
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    scored = [score(r, rng) for r in rows(args.data)]
    result = {"dataset": f"RAGBench test @ {(args.data / 'REVISION').read_text().strip()[:7]}",
              "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip(),
              "by_subset": summarise(scored)}
    for name in ("ALL", "numeric (finqa, tatqa)", "other ten"):
        print(name, json.dumps(result["by_subset"][name]))
    (HERE / "out").mkdir(exist_ok=True)
    with open(HERE / "out" / "ragbench-scored.jsonl", "w", encoding="utf-8") as f:
        for r in scored:
            f.write(json.dumps(r) + "\n")
    if args.record:
        path = HERE / "results" / f"ragbench-{result['commit']}{'-' + args.label if args.label else ''}.json"
        path.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
        print("recorded →", path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
