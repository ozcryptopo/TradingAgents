"""Monthly fund flows from SEC Form N-PORT filings (free, no key).

Every registered open-end fund and ETF files Form N-PORT, which reports, for
each of the three months in a fiscal quarter, the dollars of shares sold
(created), reinvested and redeemed. Net flow = sales + reinvestment - redemption.

How fresh: the SEC publishes one N-PORT per quarter, about 60 days after the
quarter ends, so data arrives four times a year and the latest month is two to
five months old. Use it for the long-term trend of investor money, not timing.

Coverage notes:
- Flows are per *series* (the whole fund), so a fund with ETF and mutual-fund
  share classes (e.g. Vanguard's VOO) reports all classes together.
- Unit investment trusts (SPY, QQQ, DIA, MDY) do not file N-PORT; use an
  open-end equivalent (IVV or VOO for the S&P 500, QQQM for the Nasdaq-100).

Point in time: only filings made on or before the analysis date are used.
"""

from __future__ import annotations

import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

import requests

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.files import replace_file
from tradingagents.dataflows.vendors.sec_edgar import _cached_json, _user_agent

logger = logging.getLogger(__name__)

FUND_TICKERS_URL = "https://www.sec.gov/files/company_tickers_mf.json"
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
BROWSE_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
DOC_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{adsh}/primary_doc.xml"
REQUEST_TIMEOUT = 30
DEFAULT_QUARTERS = 8  # two years of monthly flows
SEC_PAUSE_SECONDS = 0.15  # stay well under SEC's 10 requests/second

# Unit investment trusts file no N-PORT; point the analyst at an equivalent.
UIT_EQUIVALENTS = {
    "SPY": "IVV or VOO", "QQQ": "QQQM", "DIA": "no open-end equivalent", "MDY": "IJH or IVOO",
}


def _get(url: str, **kwargs) -> requests.Response:
    try:
        time.sleep(SEC_PAUSE_SECONDS)
        response = requests.get(url, headers={"User-Agent": _user_agent()}, timeout=REQUEST_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"SEC EDGAR unreachable ({type(exc).__name__})") from None
    if response.status_code == 429 or response.status_code >= 500:
        raise VendorUnavailableError(f"SEC EDGAR returned {response.status_code}")
    return response


def series_for(ticker: str) -> tuple[str, str] | None:
    """(filer CIK, series ID) for a fund ticker, or None if SEC lists no such fund."""
    table = _cached_json(FUND_TICKERS_URL, "company_tickers_mf.json")
    fields = table.get("fields") or ["cik", "seriesId", "classId", "symbol"]
    index = {name: i for i, name in enumerate(fields)}
    wanted = ticker.strip().upper()
    for row in table.get("data") or []:
        if str(row[index["symbol"]]).upper() == wanted:
            return str(int(row[index["cik"]])), str(row[index["seriesId"]])
    return None


def _filings_from_search(series_id: str) -> list[dict]:
    """NPORT-P filings naming the series, from EDGAR full-text search."""
    found: list[dict] = []
    for start in (0, 100):
        response = _get(SEARCH_URL, params={"q": f'"{series_id}"', "forms": "NPORT-P", "from": start})
        if response.status_code != 200:
            break
        hits = ((response.json().get("hits") or {}).get("hits")) or []
        for hit in hits:
            source = hit.get("_source") or {}
            adsh = source.get("adsh") or str(hit.get("_id", "")).split(":")[0]
            ciks = source.get("ciks") or []
            if adsh and ciks and source.get("file_date"):
                found.append({"adsh": adsh, "cik": str(int(ciks[0])), "filed": source["file_date"]})
        if len(hits) < 100:
            break
    return found


def _filings_from_browse(series_id: str) -> list[dict]:
    """NPORT-P filings for the series from EDGAR's company browse feed (fallback)."""
    response = _get(BROWSE_URL, params={
        "action": "getcompany", "CIK": series_id, "type": "NPORT-P",
        "dateb": "", "owner": "include", "count": "40", "output": "atom",
    })
    if response.status_code != 200:
        return []
    found = []
    try:
        root = ET.fromstring(response.content)
    except ET.ParseError:
        return []
    for entry in root.iter():
        if not entry.tag.endswith("entry"):
            continue
        values = {child.tag.split("}")[-1]: (child.text or "").strip() for child in entry.iter()}
        adsh, filed, href = values.get("accession-number"), values.get("filing-date"), values.get("filing-href", "")
        parts = href.split("/edgar/data/")
        if adsh and filed and len(parts) == 2:
            found.append({"adsh": adsh, "cik": parts[1].split("/")[0], "filed": filed})
    return found


def _parse_flows(stream) -> dict:
    """Series ID, period end, net assets and the three monthly flows from primary_doc.xml.

    Streams the document and stops after the fund-level section, so a fund's
    full holdings list (megabytes for an index fund) is never read.
    """
    out: dict = {"flows": {}}
    for _, element in ET.iterparse(stream, events=("end",)):
        tag = element.tag.split("}")[-1]
        if tag in ("seriesId", "repPdDate", "repPdEnd") and element.text:
            out.setdefault(tag, element.text.strip())
        elif tag in ("netAssets", "totAssets") and element.text and tag not in out:
            out[tag] = float(element.text)
        elif tag in ("mon1Flow", "mon2Flow", "mon3Flow"):
            out["flows"][tag] = {k: float(v) for k, v in element.attrib.items() if k in ("sales", "reinvestment", "redemption")}
            if tag == "mon3Flow":
                break
        elif tag == "invstOrSecs":
            break
        element.clear()
    return out


def _filing_summary(filing: dict) -> dict | None:
    """One filing's fund-level figures, cached on disk (filings never change)."""
    path = Path(get_config()["data_cache_dir"]) / "sec_edgar" / "nport" / f"{filing['adsh']}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    url = DOC_URL.format(cik=filing["cik"], adsh=filing["adsh"].replace("-", ""))
    response = _get(url, stream=True)
    if response.status_code != 200:
        response.close()
        return None
    response.raw.decode_content = True
    try:
        summary = _parse_flows(response.raw)
    except ET.ParseError:
        return None
    finally:
        response.close()
    summary["filed"] = filing["filed"]
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_file(path, lambda temp: Path(temp).write_text(json.dumps(summary), encoding="utf-8"))
    return summary


def _month_end(period_end: str, months_back: int) -> str:
    year, month = int(period_end[:4]), int(period_end[5:7]) - months_back
    while month < 1:
        month += 12
        year -= 1
    following = date(year + (month == 12), month % 12 + 1, 1)
    return date.fromordinal(following.toordinal() - 1).isoformat()


def _usd(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    value = abs(value)
    if value >= 1e9:
        return f"{sign}${value / 1e9:,.2f}B"
    if value >= 1e6:
        return f"{sign}${value / 1e6:,.1f}M"
    return f"{sign}${value:,.0f}"


def get_fund_flows(fund_ticker: str, as_of_date: str, months: int | None = None) -> str:
    """Monthly net flows for a U.S. fund from its N-PORT filings, as markdown.

    ``months`` is rounded up to whole quarters (one filing each); default two years.
    """
    ticker = (fund_ticker or "").strip().upper()
    if not ticker or "-" in ticker or "=" in ticker or "^" in ticker:
        return f"FUND FLOWS NOT APPLICABLE: '{fund_ticker}' is not a U.S. fund ticker."
    if ticker in UIT_EQUIVALENTS:
        return (
            f"FUND FLOWS NOT AVAILABLE FOR {ticker}: it is a unit investment trust, which files no "
            f"Form N-PORT. Call get_fund_flows with {UIT_EQUIVALENTS[ticker]} instead for the same exposure."
        )
    quarters = -(-months // 3) if months else DEFAULT_QUARTERS

    match = series_for(ticker)
    if match is None:
        return (
            f"FUND FLOWS NOT AVAILABLE: '{ticker}' is not in SEC's fund ticker list, so it is likely an "
            f"individual stock rather than a fund. For a stock, call get_fund_flows with its sector ETF "
            f"(e.g. 'SMH' for semiconductors, 'XLF' for banks). Do not estimate fund flows."
        )
    cik, series_id = match

    filings = _filings_from_search(series_id) or _filings_from_browse(series_id)
    filings = sorted(
        {f["adsh"]: f for f in filings if f["filed"] <= as_of_date}.values(),
        key=lambda f: f["filed"],
        reverse=True,
    )
    header = f"## Fund flows: {ticker} (SEC Form N-PORT, series {series_id}), monthly\n"
    if not filings:
        return header + (
            f"\nNO_DATA_AVAILABLE: no Form N-PORT filings for {ticker} found up to {as_of_date}. "
            f"Do not estimate fund flows."
        )

    months: dict[str, dict] = {}
    net_assets = None
    latest_filed = None
    for filing in filings:
        if len({m[:7] for m in months}) >= quarters * 3:
            break
        summary = _filing_summary(filing)
        if not summary or summary.get("seriesId", series_id) != series_id:
            continue
        period_end = summary.get("repPdDate") or summary.get("repPdEnd")
        if not period_end or not summary.get("flows"):
            continue
        if net_assets is None:
            net_assets, latest_filed = summary.get("netAssets"), summary["filed"]
        for back, key in ((2, "mon1Flow"), (1, "mon2Flow"), (0, "mon3Flow")):
            flow = summary["flows"].get(key)
            month = _month_end(period_end, back)
            if flow and month not in months:  # newest filing wins (amendments)
                months[month] = flow

    if not months:
        return header + (
            f"\nNO_DATA_AVAILABLE: {ticker}'s N-PORT filings carried no monthly flow figures. "
            f"Do not estimate fund flows."
        )

    rows = sorted(months.items())[-quarters * 3:]
    nets = [(m, f.get("sales", 0) + f.get("reinvestment", 0) - f.get("redemption", 0), f) for m, f in rows]
    values = [n for _, n, _ in nets]
    latest_month, latest_net, _ = nets[-1]
    pct = f" ({latest_net / net_assets * 100:+.2f}% of net assets)" if net_assets else ""

    lines = [
        header,
        f"- Latest month in public filings: {latest_month}: {_usd(latest_net)}{pct} "
        f"(filed {latest_filed}; N-PORT is published quarterly, ~60 days after quarter end, "
        f"so recent months are not yet public)",
        f"- Last 3 months: {_usd(sum(values[-3:]))}; last 6: {_usd(sum(values[-6:]))}; "
        f"last {len(values)}: {_usd(sum(values))}",
        f"- Months with net inflows: {sum(1 for v in values if v > 0)} of {len(values)}",
        f"- Net assets at latest filing: {_usd(net_assets).lstrip('+') if net_assets else 'n/a'}",
        "- Flows cover the whole fund (all share classes). Reading: persistent inflows = investors "
        "adding money over months; persistent outflows = redemptions. A long-term trend signal, not timing.",
        "",
        "| Month end | Net flow | Sales (creations) | Redemptions |",
        "| --- | --- | --- | --- |",
    ]
    for month, net, flow in reversed(nets):
        lines.append(
            f"| {month} | {_usd(net)} | {_usd(flow.get('sales', 0)).lstrip('+')} | "
            f"{_usd(flow.get('redemption', 0)).lstrip('+')} |"
        )
    return "\n".join(lines) + "\n"
