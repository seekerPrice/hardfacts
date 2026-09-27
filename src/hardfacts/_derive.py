"""Explain an Unsupported value by arithmetic over the Output's own Supported values (ADR-0007)."""

from __future__ import annotations

from decimal import Decimal

from dataclasses import replace

from ._extract import EXACT
from ._match import _same_currency
from ._model import Claim, Derivation

_ARITHMETIC_KINDS = ("quantity", "money", "percent")
_WORK_PER_CHECK = 200_000
"""Candidates the search may examine per check (one unit per operand tried, in a fixed order both ports
share). Past it, the remaining values get no Derivation: they stay Unsupported, and unexplained."""
_LARGEST_MULTIPLIER = 9
_SUMS_OF_FOUR_OR_FIVE_UP_TO = 16
"""Operands for which sums of 4 and 5 are tried: C(16, 5) = 4,368 sums per flagged value."""
_SUMS_OF_THREE_UP_TO = 60
"""Operands for which sums of 3 are tried: C(60, 3) = 34,220 sums per flagged value."""


class _Budget:
    def __init__(self, units: int) -> None:
        self.left = units

    def spend(self) -> bool:
        self.left -= 1
        return self.left >= 0


class _OutOfBudget(Exception):
    pass


def _amount(claim: Claim) -> Decimal:
    return claim.value[1] if claim.kind == "money" else claim.value


def _first_sum(operands: list[Decimal], index: dict[Decimal, int], k: int, goal: Decimal, budget: _Budget,
               start: int = 0) -> list[int] | None:
    """The lexicographically first ``k`` indices from ``start`` on whose operands sum to ``goal``.

    The same answer as scanning ``combinations(operands, k)`` in order, but the last operand is a
    lookup (O(n^(k-1))), and a branch stops once its smallest possible sum overshoots or its largest
    falls short: operands are positive and ascending."""
    if k == 1:
        i = index.get(goal)
        return [i] if i is not None and i >= start else None
    largest = Decimal(0)
    for x in operands[max(start, len(operands) - k):]:
        largest = EXACT.add(largest, x)
    if len(operands) - start < k or largest < goal:
        return None  # even the k largest operands fall short
    for i in range(start, len(operands)):
        if not budget.spend():
            raise _OutOfBudget
        if EXACT.multiply(operands[i], Decimal(k)) > goal:  # exact: 28 digits would round and mis-prune
            return None
        rest = _first_sum(operands, index, k - 1, EXACT.subtract(goal, operands[i]), budget, i + 1)
        if rest is not None:
            return [i, *rest]
    return None


class _Search:
    """The Output's Supported values, grouped once per Kind and currency, and one work budget."""

    def __init__(self, claims: tuple[Claim, ...]) -> None:
        self.claims = claims
        self.budget = _Budget(_WORK_PER_CHECK)
        self.groups: dict[tuple, tuple[list[Decimal], dict[Decimal, Claim]]] = {}
        self.multipliers: dict[Decimal, Claim] = {}
        for c in claims:
            if c.supported and c.kind == "quantity" and c.value == c.value.to_integral_value() and 2 <= c.value <= _LARGEST_MULTIPLIER:
                self.multipliers.setdefault(c.value, c)

    def operands(self, target: Claim) -> tuple[list[Decimal], dict[Decimal, Claim]]:
        key = (target.kind, target.value[0] if target.kind == "money" else None)
        if key not in self.groups:
            first: dict[Decimal, Claim] = {}
            for c in self.claims:
                if c.supported and c.kind == target.kind and _amount(c) > 0 and (
                        c.kind != "money" or _same_currency(c.value[0], target.value[0])):  # never €100 − $40
                    first.setdefault(_amount(c), c)
            self.groups[key] = (sorted(first), first)
        return self.groups[key]

    def derive(self, target: Claim) -> Derivation | None:
        """The first Derivation of ``target`` in the fixed order: differences, sums by size, products."""
        if target.kind not in _ARITHMETIC_KINDS or self.budget.left <= 0:
            return None
        goal = _amount(target)
        every, first = self.operands(target)
        operands = [x for x in every if x != goal]

        def made(symbol: str, parts: list[Claim]) -> Derivation:
            return Derivation(f" {symbol} ".join(p.text for p in parts), tuple(p.span for p in parts))

        try:
            index = {x: i for i, x in enumerate(operands)}
            for a in operands:
                if not self.budget.spend():
                    raise _OutOfBudget
                b = EXACT.subtract(a, goal)
                if b in index and b != a:
                    return made("−", [first[a], first[b]])
            largest = 5 if len(operands) <= _SUMS_OF_FOUR_OR_FIVE_UP_TO else 3 if len(operands) <= _SUMS_OF_THREE_UP_TO else 2
            for k in range(2, largest + 1):
                picked = _first_sum(operands, index, k, goal, self.budget)
                if picked is not None:
                    return made("+", [first[operands[i]] for i in picked])
            for a in operands:
                for m in sorted(self.multipliers):
                    if not self.budget.spend():
                        raise _OutOfBudget
                    if EXACT.multiply(a, m) == goal:
                        return made("×", [first[a], self.multipliers[m]])
        except _OutOfBudget:
            return None
        return None



def derive(target: Claim, claims: tuple[Claim, ...]) -> Derivation | None:
    """The first Derivation of ``target`` among ``claims`` (one search, its own budget)."""
    return _Search(claims).derive(target)


def explain(claims: tuple[Claim, ...]) -> tuple[Claim, ...]:
    """``claims`` with a Derivation on each Unsupported value that has one, within one work budget."""
    search = _Search(claims)
    return tuple(replace(c, derivation=search.derive(c)) if not c.supported and c.kind in _ARITHMETIC_KINDS else c
                 for c in claims)
