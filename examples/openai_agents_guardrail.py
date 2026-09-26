"""hardfacts as an OpenAI Agents SDK output guardrail (openai-agents 0.22).

    uv run --with openai-agents python examples/openai_agents_guardrail.py --offline   # no API key
    OPENAI_API_KEY=... uv run --with openai-agents python examples/openai_agents_guardrail.py

Tools record what they return in the run's local context (never sent to the model). The output
guardrail checks the final answer against those results and the user's message, and trips when
the answer states a value none of them contain. Arithmetic over the answer's own supported
values (a refund difference) doesn't trip it: that is `report.unexplained`, not `report.ok`.
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from typing import Any

from agents import (
    Agent,
    GuardrailFunctionOutput,
    OutputGuardrailTripwireTriggered,
    RunContextWrapper,
    Runner,
)
from agents.decorators import output_guardrail, tool

from hardfacts import check, feedback

ORDERS = {"ORD-2024-0012": {"order_id": "ORD-2024-0012", "carrier": "Pos Laju",
                            "tracking": "EN123456789MY", "eta": "2026-10-03", "shipping_fee": 12.90}}


@dataclass
class SupportContext:
    user_message: str = ""
    sources: list[Any] = field(default_factory=list)  # every tool result the agent was shown


@tool
def lookup_order(ctx: RunContextWrapper[SupportContext], order_id: str) -> str:
    """Look up an order's carrier, tracking number, ETA and shipping fee.

    Args:
        order_id: The order ID, like ORD-2024-0012.
    """
    result = ORDERS.get(order_id, {"error": "order not found"})
    ctx.context.sources.append(result)
    return json.dumps(result)


@output_guardrail
async def hard_facts_guardrail(ctx: RunContextWrapper[SupportContext], agent: Agent, output: str) -> GuardrailFunctionOutput:
    report = check(output, [ctx.context.user_message, *ctx.context.sources])
    return GuardrailFunctionOutput(
        output_info={"report": report.to_dict(), "feedback": feedback(report)},
        tripwire_triggered=bool(report.unexplained),
    )


agent = Agent[SupportContext](
    name="Order support",
    instructions="Answer order questions using the lookup_order tool. Quote tracking numbers and dates exactly.",
    tools=[lookup_order],
    output_guardrails=[hard_facts_guardrail],
)


async def answer(question: str) -> str:
    context = SupportContext(user_message=question)
    try:
        result = await Runner.run(agent, question, context=context)
        return result.final_output
    except OutputGuardrailTripwireTriggered as tripped:
        info = tripped.guardrail_result.output.output_info
        # Hand the draft to a human, or run again with info["feedback"] appended to the input.
        return "HELD FOR REVIEW:\n" + info["feedback"]


async def offline() -> None:
    """The guardrail on two drafts, without a model: what a real run would decide."""
    context = RunContextWrapper(SupportContext(user_message="Where is order ORD-2024-0012?"))
    lookup = ORDERS["ORD-2024-0012"]
    context.context.sources.append(lookup)
    for draft in ("It ships via Pos Laju, tracking EN123456789MY, arriving 3 October.",
                  "It ships via Pos Laju, tracking EN123456780MY, arriving 2 October."):
        verdict = await hard_facts_guardrail.guardrail_function(context, agent, draft)
        print("TRIPPED" if verdict.tripwire_triggered else "passed ", "|", draft)
        if verdict.tripwire_triggered:
            print("         " + verdict.output_info["feedback"].replace("\n", "\n         "))


if __name__ == "__main__":
    if "--offline" in sys.argv:
        asyncio.run(offline())
    else:
        print(asyncio.run(answer("Where is my order ORD-2024-0012 and when will it arrive?")))
