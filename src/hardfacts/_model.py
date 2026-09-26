from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ._extract import EXACT
from typing import Any


@dataclass(frozen=True)
class Evidence:
    """A Hard fact in a Source that supports a Claim."""

    source: int
    span: tuple[int, int]
    text: str


@dataclass(frozen=True)
class Derivation:
    """Arithmetic over the Output's own Supported values that gives an Unsupported Claim's Value (ADR-0007)."""

    expression: str
    """The operands as written, joined by −, + or ×: "$101.12 − $94.80"."""
    operands: tuple[tuple[int, int], ...]
    """The operands' spans in the Output."""


@dataclass(frozen=True)
class Claim:
    """A Hard fact found in the Output, with its verdict."""

    kind: str
    text: str
    span: tuple[int, int]
    value: Any
    supported: bool
    evidence: tuple[Evidence, ...] = ()
    derivation: Derivation | None = None
    """For an Unsupported number, amount or percentage: how the Output's own values give it, if they do."""


@dataclass(frozen=True)
class Report:
    """The result of one check."""

    claims: tuple[Claim, ...] = field(default_factory=tuple)
    sources: tuple[str, ...] = field(default_factory=tuple)
    """The text each Source was searched as; Evidence spans index into these."""

    @property
    def unsupported(self) -> list[Claim]:
        return [c for c in self.claims if not c.supported]

    @property
    def unexplained(self) -> list[Claim]:
        """Unsupported Claims with no Derivation: values neither a Source nor the Output's own arithmetic accounts for.
        A retry loop for a bot that must calculate (totals, price differences) can stop when this is empty."""
        return [c for c in self.claims if not c.supported and c.derivation is None]

    @property
    def ok(self) -> bool:
        return all(c.supported for c in self.claims)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "unsupported": [_claim_dict(c, with_evidence=False) for c in self.unsupported],
            "claims": [_claim_dict(c) for c in self.claims],
            "sources": list(self.sources),
        }


def _plain(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value.normalize(EXACT), "f")
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    if isinstance(value, dict):
        return {k: _plain(v) for k, v in value.items()}
    return value


def _claim_dict(claim: Claim, with_evidence: bool = True) -> dict[str, Any]:
    d: dict[str, Any] = {
        "kind": claim.kind,
        "text": claim.text,
        "span": list(claim.span),
        "value": _plain(claim.value),
        "derivation": None if claim.derivation is None else {
            "expression": claim.derivation.expression, "operands": [list(s) for s in claim.derivation.operands]},
    }
    if with_evidence:
        d["supported"] = claim.supported
        d["evidence"] = [{"source": e.source, "span": list(e.span), "text": e.text} for e in claim.evidence]
    return d
