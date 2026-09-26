"""hardfacts as LangChain agent middleware (langchain 1.x `create_agent`): verify, then retry.

    uv run --with langchain python examples/langchain_middleware.py      # offline, with a fake model

After each model turn that ends the run (no tool calls), the middleware checks the answer against
every tool result and user message in the conversation. If the answer states a value none of
them contain, it adds hardfacts' feedback as a user message and jumps back to the model, up to
`max_retries` times; after that it replaces the answer with a hand-off message. Arithmetic over
the answer's own supported values doesn't trigger a retry (`report.unexplained`).
"""

from __future__ import annotations

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, AgentState, hook_config
from langchain.messages import AIMessage, HumanMessage
from langgraph.runtime import Runtime

from hardfacts import check, feedback

RETRY_MARK = "[hardfacts] "


class HardFactsMiddleware(AgentMiddleware):
    def __init__(self, max_retries: int = 1, handoff: str = "Let me check that with a colleague and get back to you."):
        super().__init__()
        self.max_retries = max_retries
        self.handoff = handoff

    @hook_config(can_jump_to=["model"])
    def after_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        messages = state["messages"]
        answer = messages[-1]
        if not isinstance(answer, AIMessage) or answer.tool_calls:
            return None  # a tool call, not an answer yet
        sources = [m.text for m in messages if m.type in ("human", "tool") and not m.text.startswith(RETRY_MARK)]
        report = check(answer.text, sources)
        if not report.unexplained:
            return None
        retries = sum(1 for m in messages if m.type == "human" and m.text.startswith(RETRY_MARK))
        if retries >= self.max_retries:
            return {"messages": [AIMessage(self.handoff, id=answer.id)]}  # same id: replaces the answer
        return {"messages": [HumanMessage(RETRY_MARK + feedback(report))], "jump_to": "model"}


if __name__ == "__main__":
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    order = '{"order_id": "ORD-2024-0012", "tracking": "EN123456789MY", "eta": "2026-10-03"}'
    model = GenericFakeChatModel(messages=iter([
        AIMessage("Your parcel's tracking number is EN123456780MY and it arrives 2 October."),  # invents two values
        AIMessage("Your parcel's tracking number is EN123456789MY and it arrives 3 October."),  # after the feedback
    ]))
    agent = create_agent(model=model, tools=[], middleware=[HardFactsMiddleware(max_retries=1)])
    result = agent.invoke({"messages": [HumanMessage(f"Where is my order? Order record: {order}")]})
    for m in result["messages"]:
        print(f"{m.type:>5}: {m.text[:110]}")
