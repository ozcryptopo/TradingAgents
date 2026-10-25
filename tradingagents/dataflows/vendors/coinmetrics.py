"""Coin Metrics on-chain vendor (Community API, no key).

Gives the crypto analyst network activity and holder behaviour that price data
cannot show: active addresses, transaction count, hash rate, MVRV, fees, and
coins moving onto and off exchanges.

Uses the free Community API (https://docs.coinmetrics.io/api/v4/): no key,
10 requests per 6 seconds per IP. Metrics a coin or the community tier does not
serve are skipped rather than failing the request.

Point in time: the window ends the day *before* the analysis date, so a daily
value that covers the analysis day itself (and so would include hours after a
historical run's "now") is never shown.
"""

import logging
from datetime import datetime, timedelta

import requests

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.symbols import crypto_base

logger = logging.getLogger(__name__)

API_BASE = "https://community-api.coinmetrics.io/v4"
REQUEST_TIMEOUT = 30
DEFAULT_LOOKBACK_DAYS = 30
RECENT_ROWS = 7

# Metric ID -> (label, how to read it). Order is the order shown.
METRICS = {
    "CapMrktCurUSD": ("Market cap (USD)", "size"),
    "AdrActCnt": ("Active addresses", "network usage; rising = more participants"),
    "TxCnt": ("Transactions", "network usage"),
    "FeeTotNtv": ("Total fees (native units)", "demand for block space"),
    "HashRate": ("Hash rate (TH/s)", "miner commitment / security (PoW coins only)"),
    "CapMVRVCur": ("MVRV ratio", "market value / realized value; >3 historically frothy, <1 historically cheap"),
    "SplyExNtv": ("Supply held on exchanges (native)", "falling = coins leaving exchanges (holding)"),
    "FlowInExNtv": ("Exchange inflow (native)", "coins sent to exchanges; often sell-side"),
    "FlowOutExNtv": ("Exchange outflow (native)", "coins withdrawn from exchanges; often accumulation"),
}


def _request(params: dict) -> dict:
    try:
        response = requests.get(
            f"{API_BASE}/timeseries/asset-metrics", params=params, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"Coin Metrics unreachable: {exc}") from None
    if response.status_code == 429:
        raise VendorUnavailableError("Coin Metrics rate limit hit (community tier: 10 requests / 6s)")
    if response.status_code >= 500:
        raise VendorUnavailableError(f"Coin Metrics server error {response.status_code}")
    if response.status_code >= 400:
        try:
            message = response.json().get("error", {}).get("message", response.text)
        except ValueError:
            message = response.text
        return {"data": [], "error": str(message)[:300]}
    return response.json()


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    magnitude = abs(value)
    if magnitude >= 1e12:
        return f"{value / 1e12:,.2f}T"
    if magnitude >= 1e9:
        return f"{value / 1e9:,.2f}B"
    if magnitude >= 1e6:
        return f"{value / 1e6:,.2f}M"
    if magnitude >= 1000:
        return f"{value:,.0f}"
    return f"{value:,.4g}"


def _pct(new: float | None, old: float | None) -> str:
    if new is None or old in (None, 0):
        return "n/a"
    return f"{(new - old) / abs(old) * 100:+.1f}%"


def get_onchain_metrics(symbol: str, as_of_date: str, look_back_days: int | None = None) -> str:
    """On-chain activity for a crypto pair as a markdown report."""
    base = crypto_base(symbol)
    if not base:
        return (
            f"ON-CHAIN DATA NOT APPLICABLE: '{symbol}' is not a recognised USD-quoted "
            f"crypto pair. On-chain metrics exist only for crypto assets."
        )
    look_back_days = look_back_days or DEFAULT_LOOKBACK_DAYS
    end = datetime.strptime(as_of_date, "%Y-%m-%d") - timedelta(days=1)
    start = end - timedelta(days=look_back_days)

    payload = _request(
        {
            "assets": base.lower(),
            "metrics": ",".join(METRICS),
            "frequency": "1d",
            "start_time": start.strftime("%Y-%m-%d"),
            "end_time": end.strftime("%Y-%m-%d"),
            "page_size": look_back_days + 5,
            "ignore_unsupported_errors": "true",
            "ignore_forbidden_errors": "true",
        }
    )
    rows = sorted(payload.get("data") or [], key=lambda r: r.get("time", ""))
    header = (
        f"## On-chain metrics: {base} (Coin Metrics Community)\n"
        f"- Window: {start:%Y-%m-%d} to {end:%Y-%m-%d} (daily; ends the day before the analysis date)\n"
    )
    if not rows:
        reason = payload.get("error") or "no rows returned"
        return header + (
            f"\nNO_DATA_AVAILABLE: Coin Metrics returned no on-chain data for {base} ({reason}). "
            f"Do not estimate or fabricate on-chain values."
        )

    present = [m for m in METRICS if any(_num(r.get(m)) is not None for r in rows)]
    last = rows[-1]

    def value_at(metric: str, days_back: int):
        index = len(rows) - 1 - days_back
        return _num(rows[index].get(metric)) if index >= 0 else None

    lines = [
        header,
        f"Latest day: {last.get('time', '')[:10]}. Latest-day values can be preliminary (\"flash\") estimates.\n",
        "| Metric | Latest | 7d change | Change over window | How to read it |",
        "| --- | --- | --- | --- | --- |",
    ]
    for metric in present:
        label, meaning = METRICS[metric]
        latest = value_at(metric, 0)
        lines.append(
            f"| {label} | {_fmt(latest)} | {_pct(latest, value_at(metric, 7))} | "
            f"{_pct(latest, value_at(metric, len(rows) - 1))} | {meaning} |"
        )

    if "FlowInExNtv" in present and "FlowOutExNtv" in present:
        def net(days: int) -> float:
            total = 0.0
            for r in rows[-days:]:
                flow_in, flow_out = _num(r.get("FlowInExNtv")), _num(r.get("FlowOutExNtv"))
                if flow_in is not None and flow_out is not None:
                    total += flow_in - flow_out
            return total

        lines.append(
            f"\n**Net exchange flow ({base}):** last 7 days {net(7):+,.2f}, "
            f"last {len(rows)} days {net(len(rows)):+,.2f}. "
            f"Positive = more coins moved onto exchanges than off (potential sell supply); "
            f"negative = net withdrawals (often read as accumulation)."
        )

    recent = rows[-RECENT_ROWS:]
    table_metrics = [m for m in ("AdrActCnt", "TxCnt", "FlowInExNtv", "FlowOutExNtv", "CapMVRVCur") if m in present]
    if table_metrics:
        lines.append(
            "\n| Date | " + " | ".join(METRICS[m][0] for m in table_metrics) + " |\n"
            "| --- |" + " --- |" * len(table_metrics)
        )
        for r in recent:
            lines.append(
                f"| {r.get('time', '')[:10]} | "
                + " | ".join(_fmt(_num(r.get(m))) for m in table_metrics)
                + " |"
            )

    missing = [METRICS[m][0] for m in METRICS if m not in present]
    if missing:
        lines.append(f"\n_Not available for {base} on the free tier: {', '.join(missing)}._")
    return "\n".join(lines) + "\n"
