"""An ETF's top holdings and their financials, from free SEC data.

An ETF has no financial statements of its own; its fundamentals are those of
what it holds. This reads the fund's latest public Form N-PORT for its holdings
and weights, then each top holding's SEC-filed financials (the same EDGAR facts
the stock statements use), and summarises them weighted by holding size:
revenue growth, margins, leverage, cash generation, and concentration.

How fresh: N-PORT holdings are as of the fund's latest public quarter end (two
to five months old); company figures are those filed by the analysis date.
Foreign companies filing under IFRS (e.g. TSMC) have no US-GAAP facts and are
listed without figures.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from tradingagents.dataflows.config import get_config
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.files import replace_file
from tradingagents.dataflows.vendors import sec_nport
from tradingagents.dataflows.vendors.sec_edgar import (
    _ANNUAL_FORMS,
    _FACTS_URL,
    _SPANS,
    _STATEMENTS,
    _TICKERS_URL,
    _as_of,
    _cached_json,
)

logger = logging.getLogger(__name__)

DEFAULT_TOP = 10
KEPT_HOLDINGS = 50
EQUITY_CATEGORIES = {"EC", "EP"}  # common and preferred equity

_SUFFIXES = re.compile(
    r"\b(INCORPORATED|INC|CORPORATION|CORP|COMPANY|CO|LIMITED|LTD|PLC|HOLDINGS?|GROUP|"
    r"CLASS [A-Z]|CL [A-Z]|THE|NV|SA|AG|SE|LP|LLC|ADR|SPONSORED|REIT|TRUST)\b"
)


def _normalise(name: str) -> str:
    cleaned = re.sub(r"[^A-Z0-9 ]", " ", name.upper().replace("&", " AND "))
    return " ".join(_SUFFIXES.sub(" ", cleaned).split())


def _tag(element) -> str:
    return element.tag.split("}")[-1]


def _parse_holdings(stream) -> dict:
    """Series ID, period end and each holding's name, identifiers, weight and category."""
    out: dict = {"holdings": []}
    current: dict | None = None
    for event, element in ET.iterparse(stream, events=("start", "end")):
        tag = _tag(element)
        if event == "start":
            if tag == "invstOrSec":
                current = {}
            continue
        if current is None:
            if tag in ("seriesId", "repPdDate", "repPdEnd") and element.text:
                out.setdefault(tag, element.text.strip())
            elif tag == "netAssets" and element.text and "netAssets" not in out:
                out["netAssets"] = float(element.text)
            continue
        if tag in ("name", "title", "cusip", "assetCat", "payoffProfile") and element.text:
            current.setdefault(tag, element.text.strip())
        elif tag in ("pctVal", "valUSD") and element.text:
            with contextlib.suppress(ValueError):
                current[tag] = float(element.text)
        elif tag in ("isin", "ticker") and element.get("value"):
            current[tag] = element.get("value").strip()
        elif tag == "invstOrSec":
            out["holdings"].append(current)
            current = None
            element.clear()
    return out


def _holdings_for(filing: dict) -> dict | None:
    path = Path(get_config()["data_cache_dir"]) / "sec_edgar" / "nport" / f"holdings_{filing['adsh']}.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    url = sec_nport.DOC_URL.format(cik=filing["cik"], adsh=filing["adsh"].replace("-", ""))
    response = sec_nport._get(url, stream=True)
    if response.status_code != 200:
        response.close()
        return None
    response.raw.decode_content = True
    try:
        parsed = _parse_holdings(response.raw)
    except ET.ParseError:
        return None
    finally:
        response.close()
    parsed["holdings"] = sorted(parsed["holdings"], key=lambda h: h.get("pctVal") or 0, reverse=True)[:KEPT_HOLDINGS]
    parsed["filed"] = filing["filed"]
    path.parent.mkdir(parents=True, exist_ok=True)
    replace_file(path, lambda temp: Path(temp).write_text(json.dumps(parsed), encoding="utf-8"))
    return parsed


def _company_index() -> tuple[dict, dict]:
    """(ticker -> (cik, ticker), normalised name -> (cik, ticker)) from SEC's ticker list."""
    table = _cached_json(_TICKERS_URL, "company_tickers.json")
    by_ticker, by_name = {}, {}
    for entry in table.values():
        cik, ticker, title = f"{int(entry['cik_str']):010d}", entry.get("ticker", "").upper(), entry.get("title", "")
        by_ticker.setdefault(ticker, (cik, ticker))
        by_name.setdefault(_normalise(title), (cik, ticker))
    return by_ticker, by_name


def _match(holding: dict, by_ticker: dict, by_name: dict) -> tuple[str, str] | None:
    ticker = (holding.get("ticker") or "").upper()
    if ticker and ticker in by_ticker:
        return by_ticker[ticker]
    for field in ("name", "title"):
        key = _normalise(holding.get(field) or "")
        if key and key in by_name:
            return by_name[key]
    return None


def _tags(kind: str, label: str) -> tuple[str, ...]:
    return dict(_STATEMENTS[kind])[label]


def _latest(values: dict) -> tuple[str, float] | None:
    if not values:
        return None
    (end, _), value = max(values.items(), key=lambda kv: kv[0][0])
    return end, value


def _metrics(cik: str, as_of_date: str) -> dict | None:
    """Growth, margins, leverage and cash generation as filed by ``as_of_date``."""
    facts = _cached_json(_FACTS_URL.format(cik=cik), f"CIK{cik}.json")
    gaap = (facts.get("facts") or {}).get("us-gaap")
    if not gaap:
        return None
    quarterly, annual = (_SPANS["quarterly"],), (_SPANS["annual"],)
    revenue_tags = _tags("income_statement", "Revenue")
    out: dict = {}

    q_revenue, _ = _as_of(gaap, revenue_tags, as_of_date, quarterly)
    latest_q = _latest(q_revenue)
    if latest_q:
        end, value = latest_q
        year_ago = [
            v for (e, _), v in q_revenue.items()
            if 350 <= (_days(end) - _days(e)) <= 380
        ]
        out["quarter_end"] = end
        if year_ago and year_ago[0]:
            out["revenue_growth_yoy"] = (value - year_ago[0]) / abs(year_ago[0])

    fy_revenue = _latest(_as_of(gaap, revenue_tags, as_of_date, annual, _ANNUAL_FORMS)[0])
    fy_net = _latest(_as_of(gaap, _tags("income_statement", "Net Income"), as_of_date, annual, _ANNUAL_FORMS)[0])
    fy_op = _latest(_as_of(gaap, _tags("income_statement", "Operating Income"), as_of_date, annual, _ANNUAL_FORMS)[0])
    fy_ocf = _latest(_as_of(gaap, _tags("cashflow", "Operating Cash Flow"), as_of_date, annual, _ANNUAL_FORMS)[0])
    fy_capex = _latest(_as_of(gaap, _tags("cashflow", "Capital Expenditure"), as_of_date, annual, _ANNUAL_FORMS)[0])
    if fy_revenue and fy_revenue[1]:
        out["fiscal_year_end"] = fy_revenue[0]
        out["revenue"] = fy_revenue[1]
        if fy_net and fy_net[0] == fy_revenue[0]:
            out["net_margin"] = fy_net[1] / fy_revenue[1]
        if fy_op and fy_op[0] == fy_revenue[0]:
            out["operating_margin"] = fy_op[1] / fy_revenue[1]
        if fy_ocf and fy_ocf[0] == fy_revenue[0]:
            capex = fy_capex[1] if fy_capex and fy_capex[0] == fy_revenue[0] else 0.0
            out["fcf_margin"] = (fy_ocf[1] - capex) / fy_revenue[1]

    liabilities = _latest(_as_of(gaap, _tags("balance_sheet", "Total Liabilities"), as_of_date, quarterly)[0])
    equity = _latest(_as_of(gaap, _tags("balance_sheet", "Stockholders Equity"), as_of_date, quarterly)[0])
    if liabilities and equity and equity[1] > 0 and liabilities[0] == equity[0]:
        out["liabilities_to_equity"] = liabilities[1] / equity[1]
    return out or None


def _days(iso: str) -> int:
    return date.fromisoformat(iso).toordinal()


def _pct(value: float | None, signed: bool = True) -> str:
    if value is None:
        return "n/a"
    return f"{value * 100:+.1f}%" if signed else f"{value * 100:.1f}%"


def get_etf_holdings_fundamentals(fund_ticker: str, as_of_date: str, top: int | None = None) -> str:
    """Top holdings of a U.S. ETF/fund with their financials, weighted, as markdown."""
    ticker = (fund_ticker or "").strip().upper()
    if not ticker or "-" in ticker or "=" in ticker or "^" in ticker:
        return f"ETF HOLDINGS NOT APPLICABLE: '{fund_ticker}' is not a U.S. fund ticker."
    if ticker in sec_nport.UIT_EQUIVALENTS:
        return (
            f"ETF HOLDINGS NOT AVAILABLE FOR {ticker}: it is a unit investment trust, which files no "
            f"Form N-PORT. Call get_etf_holdings_fundamentals with {sec_nport.UIT_EQUIVALENTS[ticker]} instead."
        )
    top = min(max(top or DEFAULT_TOP, 1), 25)

    match = sec_nport.series_for(ticker)
    if match is None:
        return (
            f"ETF HOLDINGS NOT APPLICABLE: '{ticker}' is not in SEC's fund list; it is likely an individual "
            f"stock, whose own statements the other fundamentals tools already cover."
        )
    _, series_id = match
    filings = sec_nport._filings_from_search(series_id) or sec_nport._filings_from_browse(series_id)
    filings = sorted((f for f in filings if f["filed"] <= as_of_date), key=lambda f: f["filed"], reverse=True)

    snapshot = None
    for filing in filings[:3]:
        snapshot = _holdings_for(filing)
        if snapshot and snapshot.get("seriesId", series_id) == series_id and snapshot.get("holdings"):
            break
        snapshot = None
    header = f"## {ticker} top holdings and their financials (SEC Form N-PORT + EDGAR)\n"
    if snapshot is None:
        return header + f"\nNO_DATA_AVAILABLE: no N-PORT holdings for {ticker} filed by {as_of_date}. Do not estimate."

    holdings = snapshot["holdings"]
    equities = [h for h in holdings if h.get("assetCat") in EQUITY_CATEGORIES]
    as_of_line = (
        f"- Holdings as of {snapshot.get('repPdDate') or snapshot.get('repPdEnd')} (filed {snapshot.get('filed')})."
    )
    if not equities:
        listed = holdings[:top]
        return "\n".join([
            header,
            as_of_line,
            "- This fund holds no common stock among its largest positions (e.g. a bond or commodity fund), "
            "so there are no company financials to analyse. Its largest positions:",
            "",
            "| Holding | Weight | Category |",
            "| --- | --- | --- |",
            *(f"| {(h.get('name') or h.get('title') or '?')[:40]} | {h.get('pctVal') or 0:.2f}% | {h.get('assetCat') or 'n/a'} |"
              for h in listed),
        ]) + "\n"
    chosen = equities[:top]
    weights = [h.get("pctVal") or 0.0 for h in chosen]

    try:
        by_ticker, by_name = _company_index()
    except VendorUnavailableError:
        by_ticker, by_name = {}, {}

    rows, weighted = [], {k: [0.0, 0.0] for k in ("revenue_growth_yoy", "operating_margin", "net_margin", "fcf_margin")}
    for holding, weight in zip(chosen, weights, strict=True):
        found = _match(holding, by_ticker, by_name)
        metrics = None
        if found:
            try:
                metrics = _metrics(found[0], as_of_date)
            except VendorUnavailableError as exc:
                logger.warning("SEC facts unavailable for %s: %s", found[1], exc)
        label = found[1] if found else (holding.get("ticker") or "")
        name = holding.get("name") or holding.get("title") or "?"
        if metrics:
            for key, acc in weighted.items():
                if metrics.get(key) is not None:
                    acc[0] += metrics[key] * weight
                    acc[1] += weight
        m = metrics or {}
        leverage = f"{m['liabilities_to_equity']:.2f}x" if m.get("liabilities_to_equity") is not None else "n/a"
        note = "" if metrics else " (no SEC financials: foreign/IFRS filer or unmatched)"
        rows.append(
            f"| {name[:32]}{note} | {label or 'n/a'} | {weight:.2f}% | {_pct(m.get('revenue_growth_yoy'))} | "
            f"{_pct(m.get('operating_margin'), False)} | {_pct(m.get('net_margin'), False)} | "
            f"{_pct(m.get('fcf_margin'), False)} | {leverage} |"
        )

    top_weight = sum(weights)
    lines = [
        header,
        f"{as_of_line} Company figures as filed by {as_of_date}.",
        f"- Concentration: top {len(chosen)} = {top_weight:.1f}% of the fund; top 3 = {sum(weights[:3]):.1f}%.",
    ]
    covered = max((acc[1] for acc in weighted.values()), default=0.0)
    if covered:
        def avg(key):
            total, w = weighted[key]
            return total / w if w else None

        lines.append(
            f"- Weighted across holdings with SEC data ({covered:.1f}% of the fund): revenue growth (latest quarter YoY) "
            f"{_pct(avg('revenue_growth_yoy'))}, operating margin {_pct(avg('operating_margin'), False)}, "
            f"net margin {_pct(avg('net_margin'), False)}, free-cash-flow margin {_pct(avg('fcf_margin'), False)}."
        )
    lines += [
        "- Margins are from each company's latest annual report; growth is the latest quarter vs the same quarter a year earlier.",
        "",
        "| Holding | Ticker | Weight | Revenue growth YoY | Operating margin | Net margin | FCF margin | Liabilities/equity |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        *rows,
    ]
    return "\n".join(lines) + "\n"
