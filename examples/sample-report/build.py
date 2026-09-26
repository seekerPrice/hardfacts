"""Rebuild the sample client reports from the benchmark data (fetch it first).

    bench/fetch_ragtruth.sh && bench/fetch_taubench.sh && bench/fetch_ragbench.sh
    uv run --with pyarrow python examples/sample-report/build.py

- business-listings: 900 business write-ups by six LLMs from Yelp-style JSON records
  (RAGTruth test split, Data2txt task; each Source is the record itself).
- support-agents: every reply GPT-4o wrote as a retail and an airline support agent in
  tau-bench's published runs, with the tool definitions, policy, user turns and tool
  results it had seen by then.
- rag-answers: RAG answers over medical, legal, technical, manual and open-web documents
  (RAGBench test, CC BY 4.0, Galileo; its ten non-numeric datasets). FinQA and TAT-QA are left
  out: their answers are ratio calculations, which hardfacts flags (docs/reviews/2026-09-27-ragbench-results.md).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent / "bench"
sys.path.insert(0, str(BENCH))
from taubench import domain, tool_definitions, turns  # noqa: E402

from hardfacts._audit import audit, render_html  # noqa: E402


def business_listings():
    sources = {}
    for line in (BENCH / "data" / "source_info.jsonl").read_text(encoding="utf-8").splitlines():
        s = json.loads(line)
        sources[s["source_id"]] = s
    for line in (BENCH / "data" / "response.jsonl").read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        s = sources[r["source_id"]]
        if r["split"] == "test" and s["task_type"] == "Data2txt":
            yield {"id": f"{r['model']}#{r['id']}", "output": r["response"], "sources": [s["source_info"]]}


def support_agents():
    data = BENCH / "data" / "taubench"
    for name in ("gpt-4o-retail", "gpt-4o-airline"):
        tools = tool_definitions(data, domain(name))
        for n, run in enumerate(json.loads((data / f"{name}.json").read_text(encoding="utf-8"))):
            for i, text, seen in turns(run["traj"], tools):
                yield {"id": f"{name}/{n}/{i}", "output": text, "sources": seen}


def rag_answers():
    from ragbench import NUMERIC, rows
    for r in rows(BENCH / "data" / "ragbench"):
        if r["subset"] not in NUMERIC:
            yield {"id": f"{r['subset']}/{r['id']}", "output": r["response"] or "", "sources": [d for d in r["documents"] if d]}


REPORTS = {
    "business-listings": (business_listings, "Business write-ups from JSON records"),
    "support-agents": (support_agents, "Support-agent replies from tool results"),
    "rag-answers": (rag_answers, "RAG answers over medical, legal and technical documents"),
}

if __name__ == "__main__":
    for name, (rows, title) in REPORTS.items():
        summary = audit(rows())
        (HERE / f"{name}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (HERE / f"{name}.html").write_text(render_html(summary, title=title), encoding="utf-8")
        print(f"{name}: {summary['responses_with_unsupported']}/{summary['responses']} responses flagged, "
              f"{summary['responses_with_unexplained']} with an unexplained value")
