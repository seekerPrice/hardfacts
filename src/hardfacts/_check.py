from __future__ import annotations

import heapq
import json
from collections import defaultdict
import re
from dataclasses import replace
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Collection, Iterable, Iterator

from ._derive import explain
from ._extract import _CODES, Fact, extract, name_shape, names
from ._kinds import KINDS
from ._match import _same_currency, claim_keys, evidence_keys, supports
from ._model import Claim, Evidence, Report


def _render(source: Any) -> str:
    """A Source as the text it is searched as: strings as-is, JSON-like values as compact JSON.

    Floats are written in plain decimal notation (json.dumps would write 0.00005 as 5e-05,
    which no number reader matches), and anything that isn't JSON (datetimes) as str().
    """
    if isinstance(source, str):
        return source
    return _dumps(source)


class _Raw(str):
    """JSON punctuation already rendered, waiting on the _dumps stack."""


def _dumps(value: Any) -> str:
    """Iterative, so a source nested thousands of levels deep renders instead of hitting the recursion limit."""
    out: list[str] = []
    stack: list[Any] = [value]
    while stack:
        item = stack.pop()
        if isinstance(item, _Raw):
            out.append(item)
        elif isinstance(item, Mapping):
            entries = _javascript_order([(_key(k), v) for k, v in item.items()])
            stack.append(_Raw("}"))
            for i in range(len(entries) - 1, -1, -1):
                key, v = entries[i]
                stack.append(v)
                stack.append(_Raw((", " if i else "") + json.dumps(key, ensure_ascii=False) + ": "))
            stack.append(_Raw("{"))
        elif isinstance(item, (list, tuple)):
            stack.append(_Raw("]"))
            for i in range(len(item) - 1, -1, -1):
                stack.append(item[i])
                if i:
                    stack.append(_Raw(", "))
            stack.append(_Raw("["))
        else:
            out.append(_scalar(item))
    return "".join(out)


def _key(key: Any) -> str:
    """A dict key as JSON writes it: True is "true", None is "null", 7 is "7"."""
    if isinstance(key, str):
        return key
    if key is None or isinstance(key, (bool, float)):
        return json.dumps(key)  # json.dumps({1e20: 0}) writes "1e+20", as JavaScript does
    return _scalar(key).strip('"')


_LARGEST_ARRAY_INDEX = 2**32 - 2


def _javascript_order(entries: list[tuple[str, Any]]) -> list[tuple[str, Any]]:
    """Keys in the order JavaScript keeps them: array indices ("0", "1355937109") first, ascending,
    then the rest as inserted. JSON.parse loses any other order, so rendering this way makes a
    Source read identically in both ports (tool results often key records by numeric ID)."""
    def index(key: str) -> int | None:
        if key.isascii() and key.isdigit() and (key == "0" or key[0] != "0") and int(key) <= _LARGEST_ARRAY_INDEX:
            return int(key)
        return None
    indexed = sorted((e for e in entries if index(e[0]) is not None), key=lambda e: index(e[0]))
    return indexed + [e for e in entries if index(e[0]) is None]


def _scalar(value: Any) -> str:
    if value is None or isinstance(value, (bool, str)):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return json.dumps(value)
        text = format(Decimal(repr(value)), "f")
        if text.endswith(".0"):  # as JavaScript writes it: 1518.0 is 1518, and -0.0 is 0
            text = text[:-2]
        return "0" if text == "-0" else text
    if isinstance(value, Decimal):
        return format(value, "f")
    return json.dumps(str(value), ensure_ascii=False)


_ANCHOR = re.compile(
    r"(?:\b(?:current[\s_-]*(?:time|date)|today(?:'s\s+date)?|it(?:'s|\s+is)\s+(?:currently|now)|right\s+now|(?:time|date)\s+now\s+is|now\W{0,3}:|as\s+(?:of|at)|hari\s+ini)"
    r"|今天|现在)[^\n\d]{0,25}\Z",
    re.I | re.ASCII)
"""What introduces the conversation's own date: "The current time is 2024-05-15", {"now": "2024-07-30"}."""
_ANCHOR_YEARS = 2
"""More distinct anchor years than this and the conversation's year is ambiguous: no year is lent."""


def _with_years(evidence: list[tuple[int, Fact]], rendered: tuple[str, ...]) -> list[tuple[int, Fact]]:
    """A date a Source states without a year ("May 23rd", as a user types it) also reads with the
    conversation's year: the year of a date introduced as the current time, today or now. Never
    any year a Source happens to mention (a record's created_at, an unrelated event)."""
    anchors = sorted({r[:7] for i, e in evidence if e.kind == "date" and _ANCHOR.search(rendered[i][max(0, e.start - 40):e.start])
                      for r in e.value if r[0] != "X"})
    if not anchors or len({a[:4] for a in anchors}) > _ANCHOR_YEARS:
        return evidence
    return [(i, replace(e, value=tuple(dict.fromkeys(e.value + tuple(_nearest_year(r, a) for r in e.value
                                                                       if r.startswith("XXXX") for a in anchors)))))
            if e.kind == "date" and any(r.startswith("XXXX") for r in e.value) else (i, e) for i, e in evidence]


def _nearest_year(reading: str, anchor: str) -> str:
    """The anchor's year, or the next or previous one when that is nearer: on 2025-12-30, "Jan 2" is
    2 January 2026, and on 2026-01-03, "Dec 28" is 28 December 2025."""
    year = int(anchor[:4])
    if anchor[5] != "X" and reading[5] != "X":
        months = int(reading[5:7]) - int(anchor[5:7])
        year += 1 if months < -6 else -1 if months > 6 else 0
    return f"{year:04d}{reading[4:]}"


EVIDENCE_PER_CLAIM = 10
"""Evidence listed per Claim, first in Source order. A value that recurs thousands of times (a "5" in a table)
would otherwise make the Report itself quadratic; one piece of Evidence is enough to support a Claim."""


def _in_order(lists: list[list[int]]) -> Iterator[int]:
    """Every position in the sorted lists, once, ascending."""
    if len(lists) == 1:
        yield from lists[0]
        return
    last = -1
    for p in heapq.merge(*lists):
        if p != last:
            yield p
            last = p


def check(output: str, sources: Iterable[Any], *, kinds: Collection[str] | None = None) -> Report:
    """Check every Hard fact in ``output`` against ``sources``.

    ``sources`` are strings or JSON-like values (dicts and lists from tool calls),
    which are searched as their JSON rendering. ``kinds`` limits which Claims are
    checked, e.g. ``{"identifier", "phone", "money"}`` for a support bot.
    """
    if kinds is not None and not set(kinds) <= KINDS:
        raise ValueError(f"unknown kinds: {sorted(set(kinds) - KINDS)}; expected some of {sorted(KINDS)}")
    if isinstance(sources, (str, bytes, Mapping)):
        raise TypeError("sources must be a list of strings or JSON-like values; wrap a single source in a list")
    rendered = tuple(_render(s) for s in sources)
    evidence = _with_years([(i, fact) for i, text in enumerate(rendered) for fact in extract(text)], rendered)
    index: dict[tuple, list[int]] = defaultdict(list)
    for position, (_, e) in enumerate(evidence):
        for key in evidence_keys(e):
            index[key].append(position)
    named = _currencies_named(rendered, evidence)
    claims = []
    facts = extract(output, claims=True)
    for fact in facts:
        if kinds is not None and fact.kind not in kinds:
            continue
        found: list[Evidence] = []
        for p in _in_order([index[key] for key in claim_keys(fact) if key in index]):
            if _other_currency(fact, evidence[p], named):
                continue
            if supports(evidence[p][1], fact):
                found.append(Evidence(evidence[p][0], (evidence[p][1].start, evidence[p][1].end), evidence[p][1].text))
                if len(found) == EVIDENCE_PER_CLAIM:
                    break
        found = tuple(found)
        claims.append(Claim(fact.kind, fact.text, (fact.start, fact.end), fact.value, bool(found), found))
    if kinds is None or "name" in kinds:
        claims += _name_claims(output, rendered, [(f.start, f.end) for f in facts])
        claims.sort(key=lambda c: c.span[0])
    return Report(explain(tuple(claims)), rendered)


_CURRENCY_CODE = re.compile(rf"(?<![A-Za-z])({'|'.join(_CODES)})(?![A-Za-z])")


def _currencies_named(rendered: tuple[str, ...], evidence: list) -> dict[int, set[str]]:
    """The currencies each Source names: its amounts' currencies and codes such as "currency": "MYR"."""
    named: dict[int, set[str]] = defaultdict(set)
    for i, text in enumerate(rendered):
        named[i].update("CNY" if m.group(1) == "RMB" else m.group(1) for m in _CURRENCY_CODE.finditer(text))
    for i, e in evidence:
        if e.kind == "money" and e.value[0] is not None:
            named[i].add(e.value[0])
    return named


def _other_currency(claim: Fact, found: tuple[int, Fact], named: dict[int, set[str]]) -> bool:
    """A bare number is in the currency its Source names: {"amount": 50, "currency": "MYR"} doesn't
    support "USD 50". A Source naming no currency, or a compatible one, still does (ADR-0003)."""
    i, e = found
    if claim.kind != "money" or e.kind == "money" or claim.value[0] is None or not named[i]:
        return False
    return not any(_same_currency(claim.value[0], c) for c in named[i])


def _name_claims(output: str, rendered: tuple[str, ...], taken: list[tuple[int, int]]) -> list[Claim]:
    """Names in the Output that a same-shaped name in the Sources makes checkable (ADR-0008)."""
    by_value: dict[str, list[Evidence]] = defaultdict(list)
    for i, text in enumerate(rendered):
        for start, end, surface, value in names(text):
            by_value[value].append(Evidence(i, (start, end), surface))
    if not by_value:
        return []
    shapes = {name_shape(v) for v in by_value}
    found = []
    t = 0  # taken spans are in order and don't overlap; so are names: one forward walk
    for start, end, surface, value in names(output):
        while t < len(taken) and taken[t][1] <= start:
            t += 1
        if name_shape(value) not in shapes or (t < len(taken) and taken[t][0] < end):
            continue
        evidence = tuple(by_value.get(value, ())[:EVIDENCE_PER_CLAIM])
        found.append(Claim("name", surface, (start, end), value, bool(evidence), evidence))
    return found
