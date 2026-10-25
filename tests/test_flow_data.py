"""CryptoETF.today ETF flows, CFTC futures positioning and BusinessQuant fund
flows: parsing, point-in-time cuts, graceful degradation and routing.

All HTTP is mocked, so these run without a network connection.
"""

from unittest import mock

import pytest
import requests

from tradingagents.dataflows import router
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors import businessquant, cftc, cryptoetf


def _response(status=200, payload=None):
    response = mock.Mock()
    response.status_code = status
    response.json.return_value = payload if payload is not None else {}
    response.raise_for_status = mock.Mock()
    if status >= 400:
        response.raise_for_status.side_effect = requests.HTTPError(str(status))
    return response


# --- CryptoETF.today ----------------------------------------------------------------

_CRYPTOETF = {"symbol": "BTC", "days": [
    {"date": "2026-10-20", "totalUsdM": -50.0, "funds": [{"ticker": "IBIT", "netFlowUsdM": -20.0}, {"ticker": "FBTC", "netFlowUsdM": -30.0}]},
    {"date": "2026-10-21", "totalUsdM": 120.0, "funds": [{"ticker": "IBIT", "netFlowUsdM": 100.0}, {"ticker": "GBTC", "netFlowUsdM": 20.0}]},
    {"date": "2026-10-22", "totalUsdM": 80.0, "funds": [{"ticker": "IBIT", "netFlowUsdM": 80.0}]},
    {"date": "2026-10-23", "totalUsdM": 1250.0, "funds": [{"ticker": "FBTC", "netFlowUsdM": 1250.0}]},
]}


@pytest.mark.unit
def test_cryptoetf_reports_flows_streak_and_movers(monkeypatch):
    monkeypatch.setenv("CRYPTOETF_API_KEY", "secret")
    with mock.patch.object(cryptoetf, "is_historical", return_value=False), \
         mock.patch.object(cryptoetf.requests, "get", return_value=_response(payload=_CRYPTOETF)) as get:
        out = cryptoetf.get_etf_flows("BTC-USD", "2026-10-24")
    assert get.call_args.args[0].endswith("/flows/btc/funds")
    assert get.call_args.kwargs["headers"]["X-API-Key"] == "secret"
    assert "Latest day 2026-10-23: +$1.25B (3-day inflow streak)" in out
    assert "IBIT +$100.0M" in out


@pytest.mark.unit
def test_cryptoetf_historical_run_excludes_its_own_day(monkeypatch):
    monkeypatch.setenv("CRYPTOETF_API_KEY", "secret")
    with mock.patch.object(cryptoetf, "is_historical", return_value=True), \
         mock.patch.object(cryptoetf.requests, "get", return_value=_response(payload=_CRYPTOETF)):
        out = cryptoetf.get_etf_flows("BTC-USD", "2026-10-23")
    assert "Latest day 2026-10-22" in out


@pytest.mark.unit
def test_etf_chain_uses_cryptoetf_before_coinglass(monkeypatch):
    monkeypatch.setenv("CRYPTOETF_API_KEY", "secret")
    monkeypatch.delenv("COINGLASS_API_KEY", raising=False)
    with mock.patch.object(cryptoetf.requests, "get", return_value=_response(payload=_CRYPTOETF)):
        out = router.route_to_vendor("get_etf_flows", "BTC-USD", "2026-10-24", None)
    assert "CryptoETF.today" in out


@pytest.mark.unit
def test_cryptoetf_bad_key_is_reported(monkeypatch):
    monkeypatch.setenv("CRYPTOETF_API_KEY", "wrong")
    with mock.patch.object(cryptoetf.requests, "get", return_value=_response(status=401)), \
         pytest.raises(cryptoetf.CryptoEtfNotConfiguredError):
        cryptoetf.get_etf_flows("BTC-USD", "2026-10-24")


# --- CFTC ---------------------------------------------------------------------------

def _cot(date, lev_long, lev_short, oi=1_000_000):
    return {
        "report_date_as_yyyy_mm_dd": f"{date}T00:00:00.000",
        "market_and_exchange_names": "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE",
        "open_interest_all": str(oi),
        "lev_money_positions_long": str(lev_long), "lev_money_positions_short": str(lev_short),
        "asset_mgr_positions_long": "900000", "asset_mgr_positions_short": "100000",
        "dealer_positions_long_all": "50000", "dealer_positions_short_all": "400000",
    }


@pytest.mark.unit
def test_cftc_reports_net_positions_and_weekly_change():
    rows = [_cot("2026-10-13", 100_000, 300_000), _cot("2026-10-20", 100_000, 350_000)]
    with mock.patch.object(cftc.requests, "get", return_value=_response(payload=rows)) as get:
        out = cftc.get_futures_positioning(None, "2026-10-24", symbol="NVDA")
    where = get.call_args.kwargs["params"]["$where"]
    assert "13874A" in where                       # S&P 500 for a stock
    assert "<= '2026-10-21'" in where              # published by the analysis date
    assert "Latest report: 2026-10-20" in out
    assert "| Leveraged funds (hedge funds/CTAs) | -250,000 | -25.0% | -50,000 |" in out
    assert "| Asset managers | +800,000 | +80.0% | +0 |" in out


@pytest.mark.unit
@pytest.mark.parametrize("market, symbol, code", [
    (None, "BTC-USD", "133741"),
    ("auto", "ETH-USD", "146021"),
    ("10y", "SPY", "043602"),
    ("VIX", "", "1170E1"),
])
def test_cftc_market_resolution(market, symbol, code):
    with mock.patch.object(cftc.requests, "get", return_value=_response(payload=[])) as get:
        cftc.get_futures_positioning(market, "2026-10-24", symbol=symbol)
    assert code in get.call_args.kwargs["params"]["$where"]


@pytest.mark.unit
def test_cftc_unknown_market_is_explained_not_fetched():
    with mock.patch.object(cftc.requests, "get") as get:
        out = cftc.get_futures_positioning("lumber", "2026-10-24")
    get.assert_not_called()
    assert "Unknown futures market" in out


@pytest.mark.unit
def test_cftc_empty_is_reported_not_fabricated():
    with mock.patch.object(cftc.requests, "get", return_value=_response(payload=[])):
        out = cftc.get_futures_positioning("sp500", "2026-10-24")
    assert "NO_DATA_AVAILABLE" in out


@pytest.mark.unit
def test_cftc_outage_is_vendor_unavailable():
    with mock.patch.object(cftc.requests, "get", side_effect=requests.ConnectionError("down")), \
         pytest.raises(VendorUnavailableError):
        cftc.get_futures_positioning("sp500", "2026-10-24")


# --- BusinessQuant ------------------------------------------------------------------

_BQ = {
    "metadata": {"ticker": "SPY", "fund_name": "SPDR S&P 500 ETF Trust"},
    "summary": {},
    "data": [
        {"month_end": "2026-06-30", "net_flow_usd": 5_000_000_000, "net_assets_usd": 600_000_000_000, "value_out_of_band": False},
        {"month_end": "2026-07-31", "net_flow_usd": -2_000_000_000, "net_assets_usd": 610_000_000_000, "value_out_of_band": False},
        {"month_end": "2026-08-31", "net_flow_usd": 3_000_000_000, "net_assets_usd": 620_000_000_000, "value_out_of_band": False},
        {"month_end": "2026-09-30", "net_flow_usd": 6_200_000_000, "net_assets_usd": 620_000_000_000, "value_out_of_band": True},
    ],
}


@pytest.mark.unit
def test_businessquant_reports_monthly_flows(monkeypatch):
    monkeypatch.setenv("BUSINESSQUANT_API_KEY", "secret")
    with mock.patch.object(businessquant, "is_historical", return_value=False), \
         mock.patch.object(businessquant.requests, "get", return_value=_response(payload=_BQ)) as get:
        out = businessquant.get_fund_flows("spy", "2026-10-24")
    assert get.call_args.kwargs["params"]["ticker"] == "SPY"
    assert "SPDR S&P 500 ETF Trust" in out
    assert "Latest month 2026-09-30: +$6.20B (+1.00% of assets)" in out
    assert "Last 3 months: +$7.20B" in out
    assert "flagged unusual" in out


@pytest.mark.unit
def test_businessquant_historical_run_respects_filing_lag(monkeypatch):
    monkeypatch.setenv("BUSINESSQUANT_API_KEY", "secret")
    with mock.patch.object(businessquant, "is_historical", return_value=True), \
         mock.patch.object(businessquant.requests, "get", return_value=_response(payload=_BQ)) as get:
        out = businessquant.get_fund_flows("SPY", "2026-10-15")
    assert get.call_args.kwargs["params"]["till_date"] == "2026-08-16"
    assert "Latest month 2026-07-31" in out


@pytest.mark.unit
def test_businessquant_crypto_pair_is_not_applicable(monkeypatch):
    monkeypatch.setenv("BUSINESSQUANT_API_KEY", "secret")
    with mock.patch.object(businessquant.requests, "get") as get:
        out = businessquant.get_fund_flows("BTC-USD", "2026-10-24")
    get.assert_not_called()
    assert "NOT APPLICABLE" in out


@pytest.mark.unit
def test_businessquant_missing_key_degrades(monkeypatch):
    monkeypatch.delenv("BUSINESSQUANT_API_KEY", raising=False)
    out = router.route_to_vendor("get_fund_flows", "SPY", "2026-10-24", None)
    assert out.startswith("DATA_UNAVAILABLE") and "BUSINESSQUANT_API_KEY" in out
