"""Fail if a built release carries anything it shouldn't, or misses what it must.

    uv build && uv run python tools/check_dist.py dist

The first sdist was 7.8 MB: hatchling reads only the root .gitignore, so ts/node_modules and
local caches went in. The sdist is now an allowlist (pyproject.toml); this check keeps it one.
"""

from __future__ import annotations

import sys
import tarfile
import zipfile
from pathlib import Path

LARGEST_RELEASE = 1_000_000  # bytes; the library is ~100 KB of source
FORBIDDEN = ("node_modules", ".hypothesis", ".scratch", "bench/", "__pycache__", ".venv")


def main(folder: str) -> int:
    dist = Path(folder)
    sdists, wheels = sorted(dist.glob("*.tar.gz")), sorted(dist.glob("*.whl"))
    if not sdists or not wheels:
        print(f"check_dist: expected an sdist and a wheel in {dist}", file=sys.stderr)
        return 1
    problems = []
    for path in sdists + wheels:
        names = tarfile.open(path).getnames() if path.suffix == ".gz" else zipfile.ZipFile(path).namelist()
        if path.stat().st_size > LARGEST_RELEASE:
            problems.append(f"{path.name} is {path.stat().st_size:,} bytes")
        problems += [f"{path.name} contains {n}" for n in names if any(f in n for f in FORBIDDEN)][:5]
        for must in ("hardfacts/py.typed", "hardfacts/_check.py", "hardfacts/cli.py"):
            if not any(n.endswith(must) for n in names):
                problems.append(f"{path.name} lacks {must}")
    for p in problems:
        print(f"check_dist: {p}", file=sys.stderr)
    if not problems:
        print(f"check_dist: {', '.join(f'{p.name} ({p.stat().st_size:,} bytes)' for p in sdists + wheels)} ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "dist"))
