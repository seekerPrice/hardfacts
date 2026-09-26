"""Write the conformance fixture the TypeScript port is tested against.

    uv run python bench/export_fixture.py

Runs the Python suite with every check() call recorded (tests/conftest.py), then
writes ts/test/fixture.json: each case's inputs and the Python Report. The port
must reproduce every Report exactly; Python is the reference implementation.
"""

from __future__ import annotations

import json
import re
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        record = Path(tmp) / "cases.jsonl"
        env = {**os.environ, "HARDFACTS_RECORD": str(record)}
        subprocess.run([sys.executable, "-m", "pytest", "-q", "tests", "--ignore=tests/test_invariants.py"],
                       cwd=ROOT, env=env, check=True)
        cases = [json.loads(line) for line in record.read_text(encoding="utf-8").splitlines()]
    out = ROOT / "ts" / "test" / "fixture.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(cases, ensure_ascii=False, indent=1)
    # a lone surrogate can't be written as UTF-8; its \u escape inside a JSON string is exact
    text = re.sub("[\ud800-\udfff]", lambda m: f"\\u{ord(m.group()):04x}", text)
    out.write_text(text + "\n", encoding="utf-8")
    print(f"{len(cases)} cases → {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
