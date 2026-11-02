"""Run TradingAgents for one order."""

from __future__ import annotations

from blmi_store.config import Tier


def run_analysis(ticker: str, asset_type: str, analysis_date: str, tier: Tier) -> tuple[dict, dict]:
    """Return (final_state, run_settings). Model choice and keys come from TRADINGAGENTS_* / DEEPSEEK_API_KEY."""
    from tradingagents.default_config import DEFAULT_CONFIG
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    config = DEFAULT_CONFIG.copy()
    config["max_debate_rounds"] = tier.debate_rounds
    # The risk debate feeds only the trading decision, which customers never see; keep it minimal.
    config["max_risk_discuss_rounds"] = 1
    graph = TradingAgentsGraph(selected_analysts=tier.analysts, debug=False, config=config)
    final_state, _decision = graph.propagate(ticker, analysis_date, asset_type=asset_type)
    return final_state, graph.run_settings()
