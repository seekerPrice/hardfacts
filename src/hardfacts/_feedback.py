from __future__ import annotations

from ._kinds import KIND_NAMES
from ._model import Report


def feedback(report: Report) -> str:
    """A correction instruction for the model that wrote the Output, or "" if nothing is Unsupported.

    Meant for a verify-and-retry loop: append it as a user turn and regenerate.
    """
    if report.ok:
        return ""
    lines = [
        f'- "{c.text}" ({KIND_NAMES.get(c.kind, c.kind)}, which you computed as {c.derivation.expression}: '
        "check those are the right values to combine)" if c.derivation else f'- "{c.text}" ({KIND_NAMES.get(c.kind, c.kind)})'
        for c in report.unsupported
    ]
    return (
        "Your draft states values that do not appear in the sources you were given:\n"
        + "\n".join(lines)
        + "\n\nRewrite the draft using only values copied exactly from the sources. "
        "If the sources don't contain a value, say so instead of supplying one. "
        "Keep a value you calculated only if the calculation uses the right values, and show the calculation."
    )
