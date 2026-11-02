"""Trader and Portfolio Manager see the analysts' source reports, not only the debate."""

from unittest.mock import MagicMock

from tradingagents.agents.context import get_analyst_evidence_from_state
from tradingagents.agents.managers.portfolio_manager import create_portfolio_manager
from tradingagents.agents.trader.trader import create_trader
from tradingagents.report_pdf import short_horizon

REPORTS = {
    "market_report": "MARKET: close 77,790.08",
    "fundamentals_report": "FUNDAMENTALS: MVRV 1.447, funding +10.9%",
    "news_report": "NEWS: CFTC leveraged funds net short",
    "sentiment_report": "SENTIMENT: 4.7/10",
}


def _state(**overrides):
    state = {
        "company_of_interest": "BTC-USD",
        "asset_type": "crypto",
        "trade_date": "2026-11-02",
        "investment_plan": "Plan: Underweight",
        "trader_investment_plan": "Sell",
        "risk_debate_state": {
            "history": "debate",
            "aggressive_history": "",
            "conservative_history": "",
            "neutral_history": "",
            "latest_speaker": "Neutral",
            "current_aggressive_response": "",
            "current_conservative_response": "",
            "current_neutral_response": "",
            "count": 3,
        },
        **REPORTS,
    }
    state.update(overrides)
    return state


def _llm_capturing():
    llm = MagicMock()
    llm.with_structured_output.side_effect = NotImplementedError
    llm.invoke.return_value = MagicMock(content="**Rating**: Hold\n\nFINAL TRANSACTION PROPOSAL: **HOLD**")
    return llm


def _prompt_text(llm):
    arg = llm.invoke.call_args[0][0]
    if isinstance(arg, str):
        return arg
    return "\n".join(m["content"] for m in arg)


def test_evidence_includes_all_reports_and_note():
    text = get_analyst_evidence_from_state(_state())
    for report in REPORTS.values():
        assert report in text
    assert "not unverified assertions" in text


def test_evidence_skips_empty_and_requested():
    text = get_analyst_evidence_from_state(
        _state(news_report="", sentiment_report=None), skip=("market_report",)
    )
    assert "FUNDAMENTALS" in text
    assert "MARKET" not in text and "NEWS" not in text and "SENTIMENT" not in text
    assert get_analyst_evidence_from_state({}) == ""


def test_portfolio_manager_prompt_contains_source_reports():
    llm = _llm_capturing()
    create_portfolio_manager(llm)(_state())
    prompt = _prompt_text(llm)
    for report in REPORTS.values():
        assert report in prompt


def test_trader_prompt_contains_source_reports():
    llm = _llm_capturing()
    create_trader(llm)(_state())
    prompt = _prompt_text(llm)
    for report in REPORTS.values():
        assert report in prompt
    assert prompt.count("MARKET: close 77,790.08") == 1


def test_short_horizon_keeps_lead_phrase():
    long = "1-3 months (4-8 weeks), with the failed-rally short treated as days-to-weeks and re-evaluated"
    assert short_horizon(long) == "1-3 months"
    assert short_horizon("3-6 months") == "3-6 months"
    cut = short_horizon("Over the next several weeks while the confluence zone is tested repeatedly")
    assert cut.endswith("…") and len(cut) <= 41
