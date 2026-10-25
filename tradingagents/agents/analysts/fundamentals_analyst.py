from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.analysts.turn import take_turn
from tradingagents.agents.context import get_instrument_context_from_state, get_language_instruction
from tradingagents.agents.tools import (
    get_balance_sheet,
    get_cashflow,
    get_derivatives_data,
    get_etf_flows,
    get_fund_flows,
    get_fundamentals,
    get_income_statement,
    get_insider_transactions,
    get_onchain_metrics,
)

# What the analyst is offered for a company.
STOCK_TOOLS = (
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_insider_transactions,
    get_fund_flows,
)

# What it is offered for a crypto asset, which has no financial statements:
# the network, leveraged positioning and institutional flows instead.
CRYPTO_TOOLS = (
    get_onchain_metrics,
    get_derivatives_data,
    get_etf_flows,
)

# The tool node serves both sets; each run binds only the set for its asset.
TOOLS = STOCK_TOOLS + CRYPTO_TOOLS

STOCK_INSTRUCTIONS = (
    "You are a researcher tasked with analyzing fundamental information over the past week about a company. Please write a comprehensive report of the company's fundamental information such as financial documents, company profile, basic company financials, and company financial history to gain a full view of the company's fundamental information to inform traders. Make sure to include as much detail as possible. Provide specific, actionable insights with supporting evidence to help traders make informed decisions."
    " Make sure to append a Markdown table at the end of the report to organize key points in the report, organized and easy to read."
    " Use the available tools: `get_fundamentals` for comprehensive company analysis, `get_balance_sheet`, `get_cashflow`, and `get_income_statement` for specific financial statements, and `get_insider_transactions` for recent insider buying and selling."
    " Call `get_fund_flows` once: with no fund_ticker when the instrument is itself an ETF or fund, otherwise with its main sector ETF (e.g. 'SMH' for a chip stock, 'XLF' for a bank) to show the long-term trend of investor money into or out of its sector. These flows are months old; present them as background trend, not a near-term signal."
)

CRYPTO_INSTRUCTIONS = (
    "You are a crypto fundamentals researcher. A crypto asset has no company financials; its fundamentals are network usage, holder behaviour, leveraged positioning and institutional flows. Write a report covering:"
    " (1) on-chain activity: active addresses, transactions, fees, hash rate where it applies, MVRV valuation, and coins moving onto or off exchanges;"
    " (2) derivatives positioning: funding-rate level and trend (who is crowded, long or short) and open interest;"
    " (3) U.S. spot-ETF flows: direction, size and streak of institutional demand."
    " Call each of `get_onchain_metrics`, `get_derivatives_data` and `get_etf_flows` once, using today's date as curr_date."
    " Use only the numbers the tools return. When a tool reports data as unavailable or not applicable, say so plainly in the report and do not estimate it."
    " Explain what each signal implies for price over the next few weeks, note where signals agree or conflict, and append a Markdown table summarising each signal, its latest value, and whether it reads bullish, bearish or neutral."
)


def create_fundamentals_analyst(llm):
    def fundamentals_analyst_node(state):
        current_date = state["trade_date"]
        instrument_context = get_instrument_context_from_state(state)
        is_crypto = state.get("asset_type", "stock") == "crypto"
        tools = CRYPTO_TOOLS if is_crypto else STOCK_TOOLS

        system_message = (
            (CRYPTO_INSTRUCTIONS if is_crypto else STOCK_INSTRUCTIONS)
            + get_language_instruction()
        )

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant, collaborating with other assistants."
                    " Use the provided tools to progress towards answering the question."
                    " If you are unable to fully answer, that's OK; another assistant with different tools"
                    " will help where you left off. Execute what you can to make progress."
                    " Report what your tools support; another agent decides the trade."
                    " You have access to the following tools: {tool_names}."
                    " Today's date is {current_date}; treat it as 'now' for all analysis and tool-call date ranges. {instrument_context}\n"
                    "{system_message}",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )

        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(instrument_context=instrument_context)

        result, report = take_turn(prompt, llm, tools, state["messages"])

        return {
            "messages": [result],
            "fundamentals_report": report,
        }

    return fundamentals_analyst_node
