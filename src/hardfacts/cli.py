"""Command line.

    hardfacts check OUTPUT [SOURCE ...]      one Output against its Sources
    hardfacts report TRANSCRIPTS.jsonl       a whole dataset: {"id", "output", "sources"} per line

Exit status: 0 when every Claim is Supported (report: when the rate is under --fail-over),
1 otherwise, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from . import KINDS, check
from ._audit import audit, render_html

_LONE_SURROGATE = re.compile("[\ud800-\udfff]")


def _read(path: str) -> str:
    """Text exactly as written: a UTF-8 BOM is dropped, line endings are kept (as the TS CLI does)."""
    if path == "-":
        return sys.stdin.buffer.read().decode("utf-8-sig")
    with open(path, encoding="utf-8-sig", newline="") as f:
        return f.read()


def _load_source(path: str):
    text = _read(path)
    if path.endswith(".json"):
        try:
            return json.loads(text)
        except (ValueError, RecursionError):  # not JSON, or too deep / too long an integer to parse
            return text
    return text


def _share(text: str) -> float:
    value = float(text)
    if not 0 <= value <= 1:  # also rejects nan
        raise argparse.ArgumentTypeError(f"{text!r} is not a share between 0 and 1")
    return value


def _kinds(text: str | None) -> set[str] | None:
    """--kinds a,b → {"a", "b"}. An empty list would check nothing and pass, so it is a usage error."""
    if text is None:
        return None
    kinds = {k.strip() for k in text.split(",") if k.strip()}
    if not kinds:
        raise ValueError("--kinds needs at least one Kind")
    return kinds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hardfacts", description=__doc__.splitlines()[0], allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="check an Output against its Sources", allow_abbrev=False)
    p.add_argument("output", help="file holding the LLM Output, or - for stdin")
    p.add_argument("sources", nargs="*", help="files the model was given (.json files are parsed)")
    p.add_argument("--json", action="store_true", help="print the full Report as JSON")
    p.add_argument("--kinds", help=f"comma-separated Kinds to check (default: all of {','.join(sorted(KINDS))})")
    r = sub.add_parser("report", help="audit a JSONL file of transcripts", allow_abbrev=False)
    r.add_argument("transcripts", help='JSONL, one {"id", "output", "sources"} object per line, or - for stdin')
    r.add_argument("--json", dest="json_out", help="write the summary as JSON to this file")
    r.add_argument("--html", dest="html_out", help="write a self-contained HTML report to this file")
    r.add_argument("--kinds", help="comma-separated Kinds to check")
    r.add_argument("--fail-over", type=_share, help="exit 1 if more than this share (0-1) of responses has an Unsupported Claim")
    try:
        args = parser.parse_args(argv)
        if args.command == "report":
            return _report(args)
        output = _read(args.output)
        sources = [_load_source(s) for s in args.sources]
    except SystemExit as e:
        return 2 if e.code else 0
    except (OSError, UnicodeDecodeError) as e:
        print(f"hardfacts: {e}", file=sys.stderr)
        return 2

    try:
        report = check(output, sources, kinds=_kinds(args.kinds))
    except ValueError as e:
        print(f"hardfacts: {e}", file=sys.stderr)
        return 2
    if args.json:
        text = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
        # a lone surrogate can't be written as UTF-8; inside a JSON string its \u escape is exact
        print(_LONE_SURROGATE.sub(lambda m: f"\\u{ord(m.group()):04x}", text))
    else:
        for c in report.unsupported:
            derived = f" = {c.derivation.expression}" if c.derivation else ""
            print(f"UNSUPPORTED {c.kind:<10} {c.text!r} at {c.span[0]}-{c.span[1]}{derived}")
        n = len(report.claims)
        print(f"{n - len(report.unsupported)}/{n} hard facts supported")
    return 0 if report.ok else 1


def _rows(text: str):
    for n, line in enumerate(text.split("\n"), 1):  # not splitlines(): U+2028 inside a JSON string is not a line break
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"line {n} is not JSON: {e.msg}") from None
        if not isinstance(row, dict) or not isinstance(row.get("output"), str):
            raise ValueError(f'line {n} needs an "output" string')
        if not isinstance(row.get("sources", []), list):
            raise ValueError(f'line {n}: "sources" must be a list')
        yield row


def _report(args) -> int:
    try:
        summary = audit(list(_rows(_read(args.transcripts))), kinds=_kinds(args.kinds))
    except (OSError, UnicodeDecodeError, ValueError) as e:
        print(f"hardfacts: {e}", file=sys.stderr)
        return 2
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
    if args.html_out:
        with open(args.html_out, "w", encoding="utf-8") as f:
            f.write(render_html(summary))
    print(f"{summary['responses_with_unsupported']}/{summary['responses']} responses "
          f"({summary['unsupported_rate']:.1%}) state a hard fact with no source; "
          f"{summary['responses_with_unexplained']} of them one that isn't arithmetic on their own values")
    for kind, n in summary["unsupported_by_kind"].items():
        print(f"  {kind:<10} {n}")
    if args.fail_over is not None and summary["responses_with_unsupported"] > args.fail_over * summary["responses"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
