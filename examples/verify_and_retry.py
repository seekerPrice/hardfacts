"""Verify-and-retry with any model, no framework.

    uv run python examples/verify_and_retry.py

`generate` is a stub that behaves like a real drafting model on a bad day. On the
first attempt it invents a plausible tracking number. Swap in your own provider
call (Anthropic, OpenAI, Gemini...), since hardfacts only sees strings.
"""

from __future__ import annotations

from hardfacts import check, feedback

ORDER = {  # what the order-lookup tool returned
    "order_id": "ORD-2024-0012",
    "status": "shipped",
    "carrier": "Pos Laju",
    "tracking": "EN123456789MY",
    "eta": "2026-10-03",
}


def generate(messages: list[dict]) -> str:
    """Stand-in for a chat completion call."""
    attempt = sum(m["role"] == "assistant" for m in messages)
    if attempt == 0:
        return "Your order ORD-2024-0012 is on its way! Tracking: EN123456780MY, arriving 2 October."
    return "Your order ORD-2024-0012 is on its way with Pos Laju. Tracking: EN123456789MY, arriving 3 October."


def answer(question: str, sources: list, max_attempts: int = 3) -> str:
    messages = [
        {"role": "system", "content": f"Answer using only this order record: {sources}"},
        {"role": "user", "content": question},
    ]
    for attempt in range(1, max_attempts + 1):
        draft = generate(messages)
        report = check(draft, sources)
        print(f"attempt {attempt}: {draft}")
        if report.ok:
            return draft
        for claim in report.unsupported:
            print(f"  ✗ unsupported {claim.kind}: {claim.text!r}")
        messages += [{"role": "assistant", "content": draft}, {"role": "user", "content": feedback(report)}]
    return "I couldn't confirm those details. A colleague will follow up shortly."  # never send an unchecked draft


if __name__ == "__main__":
    print("\nsent:", answer("Where is my parcel?", [ORDER]))
