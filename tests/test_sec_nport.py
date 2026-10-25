"""SEC Form N-PORT fund flows: ticker lookup, filing discovery, streamed
parsing, point-in-time cuts and the unit-trust and stock cases.

All HTTP is mocked, so these run without a network connection.
"""

import io
from unittest import mock

import pytest

from tradingagents.dataflows import router
from tradingagents.dataflows.vendors import sec_nport

_TICKERS = {
    "fields": ["cik", "seriesId", "classId", "symbol"],
    "data": [[1100663, "S000004347", "C000012040", "IVV"], [36405, "S000002277", "C000092055", "VOO"]],
}


def _doc(period_end, flows, net_assets=500_000_000_000, series="S000004347"):
    monthly = "".join(
        f'<mon{i}Flow redemption="{r}" reinvestment="0" sales="{s}"/>' for i, (s, r) in enumerate(flows, 1)
    )
    return (
        '<?xml version="1.0"?><edgarSubmission xmlns="http://www.sec.gov/edgar/nport">'
        f"<formData><genInfo><regCik>0001100663</regCik><seriesId>{series}</seriesId>"
        f"<repPdEnd>{period_end}</repPdEnd><repPdDate>{period_end}</repPdDate></genInfo>"
        f"<fundInfo><totAssets>{net_assets + 1}</totAssets><netAssets>{net_assets}</netAssets>"
        f"<returnInfo>{monthly}</returnInfo></fundInfo>"
        "<invstOrSecs><invstOrSec><name>APPLE INC</name></invstOrSec></invstOrSecs></formData></edgarSubmission>"
    ).encode()


_SEARCH = {"hits": {"hits": [
    {"_id": "0000000001-26-000002:primary_doc.xml",
     "_source": {"adsh": "0000000001-26-000002", "ciks": ["0001100663"], "file_date": "2026-08-28"}},
    {"_id": "0000000001-26-000001:primary_doc.xml",
     "_source": {"adsh": "0000000001-26-000001", "ciks": ["0001100663"], "file_date": "2026-05-29"}},
    {"_id": "0000000001-26-000003:primary_doc.xml",   # filed after the analysis date
     "_source": {"adsh": "0000000001-26-000003", "ciks": ["0001100663"], "file_date": "2026-11-27"}},
]}}

_DOCS = {
    "000000000126000001": _doc("2026-03-31", [(3e9, 1e9), (2e9, 1e9), (4e9, 1e9)]),
    "000000000126000002": _doc("2026-06-30", [(5e9, 1e9), (1e9, 3e9), (6e9, 1e9)]),
    "000000000126000003": _doc("2026-09-30", [(9e9, 0), (9e9, 0), (9e9, 0)]),
}


def _fake_get(url, **kwargs):
    response = mock.Mock(status_code=200)
    if url == sec_nport.SEARCH_URL:
        response.json.return_value = _SEARCH
    else:
        adsh = url.split("/")[-2]
        response.raw = io.BytesIO(_DOCS[adsh])
    return response


@pytest.fixture
def sec(tmp_path):
    from tradingagents.dataflows.config import set_config

    set_config({"data_cache_dir": str(tmp_path)})
    with mock.patch.object(sec_nport, "_cached_json", return_value=_TICKERS), \
         mock.patch.object(sec_nport, "_get", side_effect=_fake_get) as get:
        yield get


@pytest.mark.unit
def test_monthly_flows_from_filings(sec):
    out = sec_nport.get_fund_flows("ivv", "2026-10-25")
    assert "series S000004347" in out
    # Latest public month is June (the September-quarter filing is not out by the date).
    assert "Latest month in public filings: 2026-06-30: +$5.00B (+1.00% of net assets)" in out
    assert "| 2026-05-31 | -$2.00B |" in out          # 1B sales - 3B redemptions
    assert "| 2026-01-31 | +$2.00B |" in out
    assert "Last 3 months: +$7.00B" in out            # 4 - 2 + 5
    assert "2026-09-30" not in out


@pytest.mark.unit
def test_cached_filings_are_not_downloaded_again(sec):
    sec_nport.get_fund_flows("IVV", "2026-10-25")
    downloads = sum(1 for c in sec.call_args_list if c.args[0] != sec_nport.SEARCH_URL)
    sec_nport.get_fund_flows("IVV", "2026-10-25")
    assert sum(1 for c in sec.call_args_list if c.args[0] != sec_nport.SEARCH_URL) == downloads


@pytest.mark.unit
def test_parser_stops_before_the_holdings_list():
    parsed = sec_nport._parse_flows(io.BytesIO(_DOCS["000000000126000002"]))
    assert parsed["seriesId"] == "S000004347"
    assert parsed["repPdDate"] == "2026-06-30"
    assert parsed["flows"]["mon2Flow"] == {"redemption": 3e9, "reinvestment": 0.0, "sales": 1e9}


@pytest.mark.unit
def test_unit_trusts_point_to_an_equivalent(sec):
    out = sec_nport.get_fund_flows("SPY", "2026-10-25")
    assert "unit investment trust" in out and "IVV or VOO" in out
    sec.assert_not_called()


@pytest.mark.unit
def test_a_stock_is_pointed_to_its_sector_etf(sec):
    out = sec_nport.get_fund_flows("NVDA", "2026-10-25")
    assert "sector ETF" in out


@pytest.mark.unit
def test_crypto_pair_is_not_applicable(sec):
    assert "NOT APPLICABLE" in sec_nport.get_fund_flows("BTC-USD", "2026-10-25")


@pytest.mark.unit
def test_month_end_arithmetic():
    assert sec_nport._month_end("2026-03-31", 2) == "2026-01-31"
    assert sec_nport._month_end("2026-03-31", 1) == "2026-02-28"
    assert sec_nport._month_end("2026-01-31", 2) == "2025-11-30"


@pytest.mark.unit
def test_default_fund_flow_vendor_is_sec_nport(sec):
    out = router.route_to_vendor("get_fund_flows", "IVV", "2026-10-25", None)
    assert "SEC Form N-PORT" in out
