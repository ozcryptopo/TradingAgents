"""Crypto enrichment vendors (Coin Metrics, Hyperliquid, CoinGlass), their
routing, and the fundamentals analyst's crypto mode.

All HTTP is mocked, so these run without a network connection.
"""

from datetime import UTC, datetime, timedelta
from unittest import mock

import pytest
import requests

from tradingagents.agents.analysts import fundamentals_analyst
from tradingagents.dataflows import router
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import coinglass, coinmetrics, hyperliquid


def _response(status=200, payload=None):
    response = mock.Mock()
    response.status_code = status
    response.json.return_value = payload if payload is not None else {}
    response.text = str(payload)
    response.raise_for_status = mock.Mock()
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(str(status))
    return response


# --- Coin Metrics -------------------------------------------------------------------

def _cm_rows(days=10, start="2026-10-10"):
    first = datetime.strptime(start, "%Y-%m-%d")
    rows = []
    for i in range(days):
        rows.append({
            "asset": "btc",
            "time": (first + timedelta(days=i)).strftime("%Y-%m-%dT00:00:00.000000000Z"),
            "AdrActCnt": str(600_000 + i * 1000),
            "TxCnt": str(500_000 + i * 500),
            "CapMVRVCur": "1.5",
            "FlowInExNtv": "1000",
            "FlowOutExNtv": "1500",
        })
    return rows


@pytest.mark.unit
def test_coinmetrics_reports_metrics_and_net_exchange_flow():
    with mock.patch.object(coinmetrics.requests, "get", return_value=_response(payload={"data": _cm_rows()})) as get:
        out = coinmetrics.get_onchain_metrics("BTC-USD", "2026-10-24", 30)
    params = get.call_args.kwargs["params"]
    assert params["assets"] == "btc"
    assert params["end_time"] == "2026-10-23"  # ends the day before the analysis date
    assert "Active addresses" in out and "MVRV ratio" in out
    # 7 days of 1000 in / 1500 out = -3,500 net
    assert "last 7 days -3,500.00" in out
    assert "Hash rate" in out  # listed as unavailable, not invented
    assert "Not available for BTC" in out


@pytest.mark.unit
def test_coinmetrics_rows_are_sorted_before_reading_latest():
    rows = list(reversed(_cm_rows()))
    with mock.patch.object(coinmetrics.requests, "get", return_value=_response(payload={"data": rows})):
        out = coinmetrics.get_onchain_metrics("BTC-USD", "2026-10-24")
    assert "Latest day: 2026-10-19" in out


@pytest.mark.unit
def test_coinmetrics_empty_is_reported_not_fabricated():
    with mock.patch.object(coinmetrics.requests, "get", return_value=_response(payload={"data": []})):
        out = coinmetrics.get_onchain_metrics("XRP-USD", "2026-10-24")
    assert "NO_DATA_AVAILABLE" in out


@pytest.mark.unit
def test_coinmetrics_rate_limit_is_vendor_unavailable():
    with mock.patch.object(coinmetrics.requests, "get", return_value=_response(status=429)), \
         pytest.raises(VendorUnavailableError):
        coinmetrics.get_onchain_metrics("BTC-USD", "2026-10-24")


@pytest.mark.unit
def test_coinmetrics_non_crypto_is_not_applicable():
    with mock.patch.object(coinmetrics.requests, "get") as get:
        out = coinmetrics.get_onchain_metrics("NVDA", "2026-10-24")
    get.assert_not_called()
    assert "NOT APPLICABLE" in out


# --- Hyperliquid --------------------------------------------------------------------

def _funding(hours=48, rate="0.0000125", end=None):
    end = end or datetime(2026, 10, 24, tzinfo=UTC)
    return [
        {"coin": "BTC", "fundingRate": rate, "premium": "0", "time": int((end - timedelta(hours=h)).timestamp() * 1000)}
        for h in range(hours, 0, -1)
    ]


_META = [
    {"universe": [{"name": "ETH"}, {"name": "BTC"}]},
    [
        {"funding": "0.00001", "openInterest": "100", "oraclePx": "3000", "markPx": "3001", "prevDayPx": "2900", "dayNtlVlm": "1000000"},
        {"funding": "0.00002", "openInterest": "20000", "oraclePx": "81000", "markPx": "81081", "prevDayPx": "80000", "dayNtlVlm": "2500000000"},
    ],
]


@pytest.mark.unit
def test_hyperliquid_live_run_reports_funding_and_open_interest():
    def post(url, json, timeout):
        return _response(payload=_META if json["type"] == "metaAndAssetCtxs" else _funding())

    with mock.patch.object(hyperliquid, "is_historical", return_value=False), \
         mock.patch.object(hyperliquid.requests, "post", side_effect=post):
        out = hyperliquid.get_derivatives_data("BTC-USD", "2026-10-24")
    assert "20,000.00 BTC" in out          # BTC's context, not ETH's
    assert "$1.62B" in out                 # 20,000 x 81,000
    assert "+0.0020%/h" in out             # current funding 0.00002
    assert "+10.9% annualized" in out      # 0.0000125 x 8760 = 10.95%
    assert "100% of 48" in out


@pytest.mark.unit
def test_hyperliquid_historical_run_withholds_live_snapshot():
    calls = []

    def post(url, json, timeout):
        calls.append(json["type"])
        return _response(payload=_funding(end=datetime(2026, 9, 1, tzinfo=UTC)))

    with mock.patch.object(hyperliquid, "is_historical", return_value=True), \
         mock.patch.object(hyperliquid.requests, "post", side_effect=post) as posted:
        out = hyperliquid.get_derivatives_data("BTC-USD", "2026-09-01")
    assert calls == ["fundingHistory"]
    end_ms = posted.call_args.kwargs["json"]["endTime"]
    assert end_ms == int(datetime(2026, 9, 1, tzinfo=UTC).timestamp() * 1000)
    assert "withheld" in out


@pytest.mark.unit
def test_hyperliquid_unreachable_is_vendor_unavailable():
    with mock.patch.object(hyperliquid.requests, "post", side_effect=requests.ConnectionError("down")), \
         pytest.raises(VendorUnavailableError):
        hyperliquid.get_derivatives_data("BTC-USD", "2026-10-24")


# --- CoinGlass ----------------------------------------------------------------------

def _etf_day(day, flow, movers):
    ts = int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp() * 1000)
    return {"timestamp": ts, "flow_usd": flow, "price_usd": 80000,
            "etf_flows": [{"etf_ticker": t, "flow_usd": f} for t, f in movers]}


_ETF = {"code": "0", "msg": "success", "data": [
    _etf_day("2026-10-20", -50_000_000, [("IBIT", -20_000_000), ("FBTC", -30_000_000)]),
    _etf_day("2026-10-21", 120_000_000, [("IBIT", 100_000_000), ("GBTC", 20_000_000)]),
    _etf_day("2026-10-22", 80_000_000, [("IBIT", 80_000_000)]),
    _etf_day("2026-10-23", 40_000_000, [("FBTC", 40_000_000)]),
]}


@pytest.mark.unit
def test_coinglass_without_key_is_not_configured(monkeypatch):
    monkeypatch.delenv("COINGLASS_API_KEY", raising=False)
    with pytest.raises(coinglass.CoinGlassNotConfiguredError):
        coinglass.get_etf_flows("BTC-USD", "2026-10-24")


@pytest.mark.unit
def test_coinglass_reports_flows_streak_and_movers(monkeypatch):
    monkeypatch.setenv("COINGLASS_API_KEY", "secret")
    with mock.patch.object(coinglass, "is_historical", return_value=False), \
         mock.patch.object(coinglass.requests, "get", return_value=_response(payload=_ETF)) as get:
        out = coinglass.get_etf_flows("BTC-USD", "2026-10-24")
    assert get.call_args.args[0].endswith("/bitcoin/flow-history")
    assert get.call_args.kwargs["headers"]["CG-API-KEY"] == "secret"
    assert "Latest day 2026-10-23: +$40.0M (3-day inflow streak)" in out
    assert "+$190.0M" in out  # 4-day total
    assert "IBIT +$100.0M" in out


@pytest.mark.unit
def test_coinglass_historical_run_excludes_its_own_day(monkeypatch):
    monkeypatch.setenv("COINGLASS_API_KEY", "secret")
    with mock.patch.object(coinglass, "is_historical", return_value=True), \
         mock.patch.object(coinglass.requests, "get", return_value=_response(payload=_ETF)):
        out = coinglass.get_etf_flows("BTC-USD", "2026-10-23")
    assert "Latest day 2026-10-22" in out
    assert "2026-10-23" not in out


@pytest.mark.unit
def test_coinglass_uncovered_coin_says_so(monkeypatch):
    monkeypatch.setenv("COINGLASS_API_KEY", "secret")
    out = coinglass.get_etf_flows("DOGE-USD", "2026-10-24")
    assert "NOT AVAILABLE" in out


# --- Routing and the analyst --------------------------------------------------------

@pytest.mark.unit
def test_missing_coinglass_key_degrades_instead_of_aborting(monkeypatch):
    monkeypatch.delenv("COINGLASS_API_KEY", raising=False)
    out = router.route_to_vendor("get_etf_flows", "BTC-USD", "2026-10-24", None)
    assert out.startswith("DATA_UNAVAILABLE")
    assert "COINGLASS_API_KEY" in out


@pytest.mark.unit
def test_crypto_tools_are_routed():
    for method in ("get_onchain_metrics", "get_derivatives_data", "get_etf_flows"):
        assert router.get_category_for_method(method) in router.OPTIONAL_CATEGORIES
        assert router.VENDOR_METHODS[method]  # has a vendor


@pytest.mark.unit
def test_tool_node_serves_both_tool_sets():
    names = {t.name for t in fundamentals_analyst.TOOLS}
    assert {"get_onchain_metrics", "get_derivatives_data", "get_etf_flows", "get_balance_sheet"} <= names


@pytest.mark.unit
@pytest.mark.parametrize("asset_type, expected, unexpected", [
    ("crypto", "get_onchain_metrics", "get_balance_sheet"),
    ("stock", "get_balance_sheet", "get_onchain_metrics"),
])
def test_analyst_binds_the_tools_for_its_asset(asset_type, expected, unexpected):
    bound = {}

    def fake_take_turn(prompt, llm, tools, messages):
        bound["tools"] = [t.name for t in tools]
        bound["system"] = prompt.messages[0].prompt.template
        reply = mock.Mock(tool_calls=[])
        return reply, "report"

    state = {"trade_date": "2026-10-24", "messages": [], "asset_type": asset_type,
             "company_of_interest": "BTC-USD", "instrument_context": ""}
    with mock.patch.object(fundamentals_analyst, "take_turn", side_effect=fake_take_turn), \
         mock.patch.object(fundamentals_analyst, "get_instrument_context_from_state", return_value=""):
        result = fundamentals_analyst.create_fundamentals_analyst(mock.Mock())(state)
    assert expected in bound["tools"] and unexpected not in bound["tools"]
    assert result["fundamentals_report"] == "report"
