"""hardfacts as a Pydantic AI output validator.

    uv sync --group examples
    uv run python examples/pydantic_ai_output_validator.py

Every tool result in the run becomes a Source. An Unsupported Claim raises ModelRetry,
so the model rewrites before anything reaches the user. The model here is Pydantic
AI's FunctionModel so the example runs offline. Replace it with e.g.
'anthropic:claude-sonnet-5' or 'google-gla:gemini-3-flash' in production.
"""

from __future__ import annotations

import os

os.environ.setdefault("PYDANTIC_AI_NO_BANNER", "1")

from pydantic_ai import Agent, ModelRetry, RunContext  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    ModelMessage, ModelRequest, ModelResponse, TextPart, ToolCallPart, ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402

from hardfacts import check, feedback  # noqa: E402


def scripted_model(messages: list[ModelMessage], info: AgentInfo) -> ModelResponse:
    """Calls the tool, then drafts an answer with a wrong ETA, then fixes it after the retry."""
    tool_returns = [p for m in messages if isinstance(m, ModelRequest) for p in m.parts if isinstance(p, ToolReturnPart)]
    retries = sum(1 for m in messages if isinstance(m, ModelRequest) for p in m.parts if p.part_kind == "retry-prompt")
    if not tool_returns:
        return ModelResponse(parts=[ToolCallPart("lookup_order", {"order_id": "ORD-2024-0012"})])
    if retries == 0:
        return ModelResponse(parts=[TextPart("Order ORD-2024-0012 ships via Pos Laju, arriving 2 October (RM 12.90 shipping).")])
    return ModelResponse(parts=[TextPart("Order ORD-2024-0012 ships via Pos Laju, arriving 3 October (RM 12.90 shipping).")])


agent = Agent(FunctionModel(scripted_model), instructions="Answer only from tool results.")


@agent.tool_plain
def lookup_order(order_id: str) -> dict:
    return {"order_id": order_id, "carrier": "Pos Laju", "eta": "2026-10-03", "shipping_fee": 12.90}


@agent.output_validator
def every_hard_fact_has_a_source(ctx: RunContext, output: str) -> str:
    if ctx.partial_output:
        return output
    sources = [
        part.content
        for message in ctx.messages
        if isinstance(message, ModelRequest)
        for part in message.parts
        if isinstance(part, ToolReturnPart)
    ]
    report = check(output, sources)
    if not report.ok:
        print("validator:", [c.text for c in report.unsupported], "→ retry")
        raise ModelRetry(feedback(report))
    return output


if __name__ == "__main__":
    result = agent.run_sync("When does my order ORD-2024-0012 arrive?")
    print("final:", result.output)
