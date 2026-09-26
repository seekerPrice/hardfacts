"""Set HARDFACTS_RECORD=<path> to record every check() the suite makes as a conformance case.

The recorded cases (inputs plus the Python Report) are the shared fixture the
TypeScript port must reproduce exactly: `uv run python bench/export_fixture.py`.
"""

import json
import os

import pytest

import hardfacts

RECORD = os.environ.get("HARDFACTS_RECORD")


@pytest.fixture(autouse=True)
def _record_checks(monkeypatch, request):
    if not RECORD:
        yield
        return
    real = hardfacts.check

    def recording(output, sources, *, kinds=None):
        report = real(output, sources, kinds=kinds)  # raises before recording on invalid sources
        sources = list(sources)
        case = {"test": request.node.nodeid, "output": output, "sources": sources,
                "kinds": sorted(kinds) if kinds is not None else None, "report": report.to_dict(),
                "feedback": hardfacts.feedback(report)}
        with open(RECORD, "a", encoding="utf-8") as f:
            f.write(json.dumps(case, default=str) + "\n")  # ASCII escapes keep lone surrogates exact
        return report

    for module in [m for name, m in list(__import__("sys").modules.items()) if name.startswith("test_")]:
        if getattr(module, "check", None) is real:
            monkeypatch.setattr(module, "check", recording)
    yield
