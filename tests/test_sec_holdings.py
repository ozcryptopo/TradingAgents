"""ETF top holdings and their SEC financials: holdings parsing, ticker
matching, weighted metrics, bond funds, and routing.

All HTTP is mocked, so these run without a network connection.
"""

import io
from unittest import mock

import pytest

from tradingagents.dataflows import router
from tradingagents.dataflows.vendors import sec_holdings, sec_nport


def _holding(name, pct, cat="EC", ticker=None):
    tick = f'<ticker value="{ticker}"/>' if ticker else ""
    ident = f'<identifiers><isin value="US0000000000"/>{tick}</identifiers>'
    return (f"<invstOrSec><name>{name}</name><title>{name} common</title><cusip>000000000</cusip>{ident}"
            f"<balance>100</balance><valUSD>{pct * 1e8}</valUSD><pctVal>{pct}</pctVal>"
            f"<payoffProfile>Long</payoffProfile><assetCat>{cat}</assetCat></invstOrSec>")


def _doc(holdings):
    return ('<?xml version="1.0"?><edgarSubmission xmlns="http://www.sec.gov/edgar/nport"><formData>'
            "<genInfo><seriesId>S000000001</seriesId><repPdDate>2026-06-30</repPdDate></genInfo>"
            "<fundInfo><netAssets>1000000000</netAssets></fundInfo>"
            f"<invstOrSecs>{''.join(holdings)}</invstOrSecs></formData></edgarSubmission>").encode()


_EQUITY_DOC = _doc([
    _holding("NVIDIA Corp", 20.0),
    _holding("Broadcom Inc", 10.0, ticker="AVGO"),
    _holding("Taiwan Semiconductor Manufacturing Co Ltd", 12.0),
    _holding("Cash Collateral", 1.0, cat="STIV"),
])

_BOND_DOC = _doc([_holding("United States Treasury Bond 4.25% 2054", 5.0, cat="DBT")])

_TICKERS = {"0": {"cik_str": 1045810, "ticker": "NVDA", "title": "NVIDIA CORP"},
            "1": {"cik_str": 1730168, "ticker": "AVGO", "title": "Broadcom Inc."}}


def _fact(end, val, start=None, form="10-Q", filed=None):
    fact = {"end": end, "val": val, "form": form, "filed": filed or end}
    if start:
        fact["start"] = start
    return fact


def _facts(q_now, q_year_ago, fy_rev, fy_net, fy_op, ocf, capex, liabilities, equity):
    usd = lambda *facts: {"units": {"USD": list(facts)}}  # noqa: E731
    return {"facts": {"us-gaap": {
        "RevenueFromContractWithCustomerExcludingAssessedTax": usd(
            _fact("2026-04-30", q_now, "2026-02-01", filed="2026-05-28"),
            _fact("2025-04-30", q_year_ago, "2025-02-01", filed="2025-05-28"),
            _fact("2026-01-31", fy_rev, "2025-02-01", form="10-K", filed="2026-02-25"),
        ),
        "NetIncomeLoss": usd(_fact("2026-01-31", fy_net, "2025-02-01", form="10-K", filed="2026-02-25")),
        "OperatingIncomeLoss": usd(_fact("2026-01-31", fy_op, "2025-02-01", form="10-K", filed="2026-02-25")),
        "NetCashProvidedByUsedInOperatingActivities": usd(
            _fact("2026-01-31", ocf, "2025-02-01", form="10-K", filed="2026-02-25")),
        "PaymentsToAcquirePropertyPlantAndEquipment": usd(
            _fact("2026-01-31", capex, "2025-02-01", form="10-K", filed="2026-02-25")),
        "Liabilities": usd(_fact("2026-04-30", liabilities, filed="2026-05-28")),
        "StockholdersEquity": usd(_fact("2026-04-30", equity, filed="2026-05-28")),
    }}}


def _yahoo(ticker):
    # NVDA per Yahoo: same FY operating margin (confirms) and a newer quarter.
    return {
        "q_revenue": {"2026-07-31": 50e9, "2026-04-30": 40e9, "2025-07-31": 22e9, "2025-04-30": 20e9},
        "revenue": {"2026-01-31": 130e9}, "operating": {"2026-01-31": 80e9}, "net": {"2026-01-31": 70e9},
    }


_FACTS = {
    "0001045810": _facts(40e9, 20e9, 130e9, 70e9, 80e9, 60e9, 4e9, 30e9, 80e9),   # NVDA: +100% growth
    "0001730168": _facts(15e9, 12e9, 55e9, 10e9, 20e9, 20e9, 1e9, 70e9, 70e9),    # AVGO: +25%
}


def _cached_json(url, name):
    if name == "company_tickers.json":
        return _TICKERS
    return _FACTS[name[3:13]]


@pytest.fixture
def sec(tmp_path):
    from tradingagents.dataflows.config import set_config

    set_config({"data_cache_dir": str(tmp_path)})
    docs = {"doc": _EQUITY_DOC}

    def fake_get(url, **kwargs):
        return mock.Mock(status_code=200, raw=io.BytesIO(docs["doc"]))

    with mock.patch.object(sec_nport, "series_for", return_value=("1", "S000000001")), \
         mock.patch.object(sec_nport, "_filings_from_search",
                           return_value=[{"adsh": "0000000001-26-000001", "cik": "1", "filed": "2026-08-28"}]), \
         mock.patch.object(sec_nport, "_get", side_effect=fake_get), \
         mock.patch.object(sec_holdings, "_cached_json", side_effect=_cached_json), \
         mock.patch("tradingagents.dataflows.verify.yahoo_statements", side_effect=_yahoo):
        yield docs


@pytest.mark.unit
def test_top_holdings_with_weighted_financials(sec):
    out = sec_holdings.get_etf_holdings_fundamentals("SMH", "2026-10-25")
    assert "Holdings as of 2026-06-30" in out
    assert "top 3 = 42.0%" in out                       # 20 + 12 + 10; cash excluded
    nvda = next(line for line in out.splitlines() if line.startswith("| NVIDIA"))
    assert "| NVDA | 20.00% | +100.0% | 2026-04 | 61.5% | 53.8% | 43.1% | 0.38x |" in nvda
    assert "| AVGO | 10.00% | +25.0% |" in out          # matched by the filing's ticker
    assert "Taiwan Semiconductor" in out and "no SEC financials" in out
    # Weighted over NVDA (20) and AVGO (10): growth (100*20 + 25*10) / 30 = 75%
    assert "revenue growth (latest quarter YoY) +75.0%" in out
    assert "Cash Collateral" not in out


@pytest.mark.unit
def test_bond_fund_lists_holdings_without_financials(sec):
    sec["doc"] = _BOND_DOC
    out = sec_holdings.get_etf_holdings_fundamentals("TLT", "2026-10-25")
    assert "holds no common stock" in out
    assert "United States Treasury Bond" in out


@pytest.mark.unit
def test_unit_trust_points_to_equivalent():
    out = sec_holdings.get_etf_holdings_fundamentals("QQQ", "2026-10-25")
    assert "QQQM" in out


@pytest.mark.unit
def test_stock_is_not_applicable(sec):
    with mock.patch.object(sec_nport, "series_for", return_value=None):
        out = sec_holdings.get_etf_holdings_fundamentals("NVDA", "2026-10-25")
    assert "NOT APPLICABLE" in out


@pytest.mark.unit
def test_name_normalisation_matches_sec_titles():
    assert sec_holdings._normalise("NVIDIA Corp") == sec_holdings._normalise("NVIDIA CORP")
    assert sec_holdings._normalise("Broadcom Inc.") == sec_holdings._normalise("BROADCOM INC")
    assert sec_holdings._normalise("Alphabet Inc Class A") == sec_holdings._normalise("Alphabet Inc.")


@pytest.mark.unit
def test_routed(sec):
    out = router.route_to_vendor("get_etf_holdings_fundamentals", "SMH", "2026-10-25", None)
    assert "top holdings and their financials" in out


@pytest.mark.unit
def test_state_of_incorporation_tag_is_ignored():
    assert sec_holdings._normalise("APPLIED MATERIALS INC /DE") == sec_holdings._normalise("Applied Materials Inc")
    assert sec_holdings._normalise("KLA CORP /DE/") == sec_holdings._normalise("KLA Corp")


@pytest.mark.unit
def test_liabilities_derived_when_not_tagged_and_net_income_fallback(tmp_path):
    usd = lambda *facts: {"units": {"USD": list(facts)}}  # noqa: E731
    facts = {"facts": {"us-gaap": {
        "Revenues": usd(_fact("2025-12-31", 100e9, "2025-01-01", form="10-K", filed="2026-02-01")),
        "NetIncomeLossAvailableToCommonStockholdersBasic": usd(
            _fact("2025-12-31", 20e9, "2025-01-01", form="10-K", filed="2026-02-01")),
        "LiabilitiesAndStockholdersEquity": usd(_fact("2026-03-31", 150e9, filed="2026-05-01")),
        "StockholdersEquity": usd(_fact("2026-03-31", 100e9, filed="2026-05-01")),
    }}}
    with mock.patch.object(sec_holdings, "_cached_json", return_value=facts):
        m = sec_holdings._metrics("0000000001", "2026-10-25")
    assert m["net_margin"] == pytest.approx(0.2)
    assert m["liabilities_to_equity"] == pytest.approx(0.5)   # (150 - 100) / 100


@pytest.mark.unit
def test_unusual_figures_are_cross_checked(sec):
    out = sec_holdings.get_etf_holdings_fundamentals("SMH", "2026-10-25")
    assert "### Checks on unusual figures" in out
    assert "NVDA: operating margin 61.5% (fiscal year to 2026-01-31) CONFIRMED by Yahoo Finance (61.5%)" in out
    assert "NVDA: net margin 53.8% (fiscal year to 2026-01-31) CONFIRMED" in out
