"""The model the editing and quality-control agents use: the run's deep-thinking model (DeepSeek by default)."""

from __future__ import annotations

from typing import Callable

LLMCall = Callable[[str, str], str]


def build_llm() -> LLMCall:
    from langchain_core.messages import HumanMessage, SystemMessage

    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.llm_clients.factory import create_tier_client

    model = create_tier_client(DEFAULT_CONFIG.copy(), "deep").get_llm()

    def call(system: str, user: str) -> str:
        reply = model.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        content = reply.content
        if isinstance(content, list):
            content = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in content)
        return str(content).strip()

    return call
