"""Dataset-level audit: how often, and how, a system's outputs state unsupported hard facts."""

from __future__ import annotations

import html
from collections import Counter
from typing import Any, Collection, Iterable

from ._check import check
from ._kinds import KIND_NAMES

MAX_EXAMPLES = 200


def audit(rows: Iterable[dict[str, Any]], *, kinds: Collection[str] | None = None) -> dict[str, Any]:
    """Check every row (``{"id", "output", "sources"}``) and summarise the Unsupported Claims."""
    responses = flagged = unexplained = derived = claims = 0
    by_kind: Counter[str] = Counter()
    claims_by_kind: Counter[str] = Counter()
    examples = []
    for n, row in enumerate(rows, 1):
        report = check(row["output"], row.get("sources", []), kinds=kinds)
        responses += 1
        claims += len(report.claims)
        claims_by_kind.update(c.kind for c in report.claims)
        flagged += not report.ok
        unexplained += any(c.derivation is None for c in report.unsupported)
        for c in report.unsupported:
            by_kind[c.kind] += 1
            derived += c.derivation is not None
            if len(examples) < MAX_EXAMPLES:
                a, b = c.span
                examples.append({
                    "id": row.get("id", n), "kind": c.kind, "text": c.text,
                    "before": row["output"][max(0, a - 90):a], "after": row["output"][b:b + 60],
                    "derivation": c.derivation.expression if c.derivation else None,
                })
    return {
        "responses": responses,
        "responses_with_unsupported": flagged,
        "unsupported_rate": round(flagged / responses, 4) if responses else 0.0,
        "responses_with_unexplained": unexplained,
        "unsupported_with_derivation": derived,
        "hard_facts": claims,
        "hard_facts_by_kind": dict(claims_by_kind.most_common()),
        "unsupported_by_kind": dict(by_kind.most_common()),
        "examples": examples,
    }


def render_html(summary: dict[str, Any], title: str = "Hard-fact audit") -> str:
    """A self-contained HTML page (no scripts, no external assets) for a client or a PR comment."""
    e = html.escape
    rows = "".join(
        f"<tr><td>{e(KIND_NAMES.get(k, k))}</td><td class=n>{summary['hard_facts_by_kind'].get(k, 0)}</td>"
        f"<td class=n>{summary['unsupported_by_kind'].get(k, 0)}</td></tr>"
        for k in summary["hard_facts_by_kind"]
    )
    examples = "".join(
        f"<li><span class=id>{e(str(x['id']))} · {e(KIND_NAMES.get(x['kind'], x['kind']))}</span>"
        f"<p>…{e(x['before'])}<mark>{e(x['text'])}</mark>{e(x['after'])}…</p>"
        + (f"<p class=work>computed as {e(x['derivation'])}: check that these are the right values to combine</p>"
           if x.get("derivation") else "")
        + "</li>"
        for x in summary["examples"]
    )
    total_unsupported = sum(summary["unsupported_by_kind"].values())
    rate = summary["unsupported_rate"] * 100
    return f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<style>
body{{font:15px/1.55 system-ui,-apple-system,"Segoe UI",sans-serif;color:#18212c;background:#fbfbf8;margin:0;padding:32px 20px}}
main{{max-width:860px;margin:0 auto}} h1{{font:700 1.9rem/1.2 Georgia,serif;margin:0 0 6px}}
.big{{font:700 3rem/1 Georgia,serif;color:#c2331d;margin:18px 0 4px}} .muted{{color:#5a6470}}
table{{border-collapse:collapse;width:100%;margin:22px 0}} th,td{{text-align:left;padding:7px 10px 7px 0;border-bottom:1px solid #d6dad2}}
th{{font-size:.75rem;letter-spacing:.08em;text-transform:uppercase;color:#5a6470;border-bottom:1px solid #18212c}}
.n{{text-align:right;font-variant-numeric:tabular-nums}} ol{{padding-left:1.2em}} li{{margin:0 0 14px}}
.id{{font:.78rem ui-monospace,Menlo,monospace;color:#5a6470}} li p{{margin:2px 0 0}}
mark{{background:#fbe4df;color:#c2331d;text-decoration:line-through;text-decoration-thickness:2px;padding:0 2px}}
.work{{font-size:.85rem;color:#5a6470}}
</style>
<main>
<h1>{e(title)}</h1>
<p class="muted">Every number, date, amount, contact detail and ID in each response, checked against the sources that response was given (hardfacts).</p>
<div class="big">{rate:.1f}%</div>
<p>of responses ({summary['responses_with_unsupported']:,} of {summary['responses']:,}) state at least one hard fact that no source contains.
{summary['responses_with_unexplained']:,} of them state one that isn't arithmetic on values the response itself states and the sources support.
{summary['unsupported_with_derivation']:,} of the {total_unsupported:,} unsupported values are such arithmetic, shown with the working below.</p>
<table><thead><tr><th>Kind</th><th class=n>Hard facts stated</th><th class=n>With no source</th></tr></thead><tbody>{rows}</tbody></table>
<h2>Examples</h2>
<ol>{examples}</ol>
<p class="muted">Unsupported means no source states the value. That covers invented values, and also correct values the model computed or brought in from outside the sources. Review the examples before drawing conclusions.</p>
</main></html>
"""
