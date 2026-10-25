"""BusinessQuant fund-flow vendor: monthly flows for any U.S. ETF or mutual fund.

Net creations/redemptions per month for SPY, QQQ, TLT, sector ETFs and so on,
taken from the funds' SEC monthly filings. Monthly, so it shows the trend of
investor money, not day-to-day moves.

Reads ``BUSINESSQUANT_API_KEY`` (free at https://businessquant.com). Without it
the vendor raises ``VendorNotConfiguredError`` and the run carries on.

Point in time: monthly filings become public with a lag, so a historical run
sees only months ending at least ``FILING_LAG_DAYS`` before its date.
"""

import logging
import os
from datetime import datetime, timedelta

import requests

from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError

logger = logging.getLogger(__name__)

API_URL = "https://data.businessquant.com/funds/flows"
REQUEST_TIMEOUT = 30
DEFAULT_MONTHS = 12
FILING_LAG_DAYS = 60


class BusinessQuantNotConfiguredError(VendorNotConfiguredError):
    """BUSINESSQUANT_API_KEY is not set."""


def get_api_key() -> str:
    key = os.getenv("BUSINESSQUANT_API_KEY")
    if not key:
        raise BusinessQuantNotConfiguredError(
            "BUSINESSQUANT_API_KEY is not set, so ETF/fund flows are unavailable. "
            "Add BUSINESSQUANT_API_KEY=... to your .env (free key at businessquant.com) to enable them."
        )
    return key


def _request(params: dict) -> dict:
    key = get_api_key()
    try:
        response = requests.get(API_URL, params={**params, "api_key": key}, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"BusinessQuant unreachable: {str(exc).replace(key, '***')}") from None
    if response.status_code == 429 or response.status_code >= 500:
        raise VendorUnavailableError(f"BusinessQuant returned {response.status_code}")
    if response.status_code in (401, 403):
        # The body says why: a bad key, or a plan without fund flows.
        try:
            note = (response.json().get("metadata") or {}).get("note", "")
        except ValueError:
            note = ""
        raise BusinessQuantNotConfiguredError(
            f"BusinessQuant refused the request ({response.status_code}): "
            f"{note or 'check BUSINESSQUANT_API_KEY'}"
        )
    if response.status_code in (400, 404):
        return {}
    response.raise_for_status()
    return response.json()


def _usd(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    value = abs(value)
    if value >= 1e9:
        return f"{sign}${value / 1e9:,.2f}B"
    if value >= 1e6:
        return f"{sign}${value / 1e6:,.1f}M"
    return f"{sign}${value:,.0f}"


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_fund_flows(fund_ticker: str, as_of_date: str, months: int | None = None) -> str:
    """Monthly net flows for a U.S. ETF or mutual fund, as markdown."""
    ticker = (fund_ticker or "").strip().upper()
    if not ticker or "-" in ticker or "=" in ticker:
        return f"FUND FLOWS NOT APPLICABLE: '{fund_ticker}' is not a U.S. fund ticker."
    months = months or DEFAULT_MONTHS
    cutoff = as_of_date
    if is_historical(as_of_date):
        cutoff = (datetime.strptime(as_of_date, "%Y-%m-%d") - timedelta(days=FILING_LAG_DAYS)).strftime("%Y-%m-%d")
    start = (datetime.strptime(cutoff, "%Y-%m-%d") - timedelta(days=31 * (months + 1))).strftime("%Y-%m-%d")

    payload = _request({"ticker": ticker, "from_date": start, "till_date": cutoff})
    meta = payload.get("metadata") or {}
    rows = []
    for row in payload.get("data") or []:
        month = str(row.get("month_end", ""))[:10]
        flow = _num(row.get("net_flow_usd"))
        if month and flow is not None and month <= cutoff:
            rows.append((month, flow, _num(row.get("net_assets_usd")), bool(row.get("value_out_of_band"))))
    rows.sort(key=lambda r: r[0])
    rows = rows[-months:]

    name = meta.get("fund_name") or ticker
    header = f"## Fund flows: {ticker} ({name}), monthly (BusinessQuant, from SEC filings)\n"
    if not rows:
        return header + (
            f"\nNO_DATA_AVAILABLE: no monthly flow data for {ticker} up to {cutoff}. "
            f"It may be an individual stock rather than a fund. Do not estimate fund flows."
        )

    flows = [f for _, f, _, _ in rows]
    latest_month, latest_flow, latest_assets, _ = rows[-1]
    pct = f" ({latest_flow / latest_assets * 100:+.2f}% of assets)" if latest_assets else ""
    lines = [
        header,
        f"- Latest month {latest_month}: {_usd(latest_flow)}{pct}",
        f"- Last 3 months: {_usd(sum(flows[-3:]))}",
        f"- Last {len(flows)} months: {_usd(sum(flows))}",
        f"- Months with inflows: {sum(1 for f in flows if f > 0)} of {len(flows)}",
        "- Reading: persistent inflows = investors adding money; outflows = redemptions. "
        "Monthly data lags; it shows the trend, not this week's moves.",
        "",
        "| Month end | Net flow | Net assets |",
        "| --- | --- | --- |",
    ]
    for month, flow, assets, odd in reversed(rows):
        flag = " (flagged unusual)" if odd else ""
        lines.append(f"| {month} | {_usd(flow)}{flag} | {_usd(assets).lstrip('+') if assets else 'n/a'} |")
    return "\n".join(lines) + "\n"
