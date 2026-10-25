"""CryptoETF.today spot-ETF flow vendor (free key).

Daily net flows for U.S. spot crypto ETFs, broken down by fund, for 16 coins
(BTC, ETH, SOL, XRP, DOGE, LINK, AVAX, LTC, DOT, HBAR, SUI, BNB, NEAR, TRX,
ZEC, HYPE). The free key serves the last 30 days.

Reads ``CRYPTOETF_API_KEY`` (free at https://cryptoetf.today). Without it the
vendor raises ``VendorNotConfiguredError`` and the router tries the next
etf_flows vendor (CoinGlass), or reports ETF flows as unavailable.

Point in time: a day's flows are known only after that U.S. session closes, so
a historical run sees flows strictly before its date.
"""

import logging
import os

import requests

from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError
from tradingagents.dataflows.symbols import crypto_base

logger = logging.getLogger(__name__)

API_BASE = "https://api.cryptoetf.today/api/v1"
REQUEST_TIMEOUT = 30
DEFAULT_LOOKBACK_DAYS = 14
TOP_FUNDS = 4

COVERED = {
    "BTC", "ETH", "SOL", "XRP", "DOGE", "LINK", "AVAX", "LTC",
    "DOT", "HBAR", "SUI", "BNB", "NEAR", "TRX", "ZEC", "HYPE",
}


class CryptoEtfNotConfiguredError(VendorNotConfiguredError):
    """CRYPTOETF_API_KEY is not set."""


def get_api_key() -> str:
    key = os.getenv("CRYPTOETF_API_KEY")
    if not key:
        raise CryptoEtfNotConfiguredError(
            "CRYPTOETF_API_KEY is not set, so spot-ETF flows are unavailable. "
            "Add CRYPTOETF_API_KEY=... to your .env (free key at cryptoetf.today) to enable them."
        )
    return key


def _request(path: str) -> dict:
    key = get_api_key()
    try:
        response = requests.get(
            f"{API_BASE}/{path}",
            headers={"X-API-Key": key, "accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"CryptoETF.today unreachable: {str(exc).replace(key, '***')}") from None
    if response.status_code == 429 or response.status_code >= 500:
        raise VendorUnavailableError(f"CryptoETF.today returned {response.status_code}")
    if response.status_code in (401, 403):
        raise CryptoEtfNotConfiguredError(
            f"CryptoETF.today rejected the API key ({response.status_code}); check CRYPTOETF_API_KEY."
        )
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    return response.json()


def _usd_m(value_m: float) -> str:
    """A flow given in USD millions, formatted."""
    sign = "+" if value_m >= 0 else "-"
    value_m = abs(value_m)
    if value_m >= 1000:
        return f"{sign}${value_m / 1000:,.2f}B"
    return f"{sign}${value_m:,.1f}M"


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_etf_flows(symbol: str, as_of_date: str, look_back_days: int | None = None) -> str:
    """Daily U.S. spot-ETF net flows for a crypto pair, as markdown."""
    base = crypto_base(symbol)
    if not base:
        return f"ETF FLOWS NOT APPLICABLE: '{symbol}' is not a recognised USD-quoted crypto pair."
    if base not in COVERED:
        return (
            f"ETF FLOWS NOT AVAILABLE: no U.S. spot-ETF flow series is tracked for {base}. "
            f"Do not estimate ETF flows."
        )
    look_back_days = look_back_days or DEFAULT_LOOKBACK_DAYS
    payload = _request(f"flows/{base.lower()}/funds")

    include_as_of_day = not is_historical(as_of_date)
    days = []
    for row in payload.get("days") or []:
        day = str(row.get("date", ""))[:10]
        total = _num(row.get("totalUsdM"))
        if total is None:
            total = _num(row.get("netFlowUsdM"))
        if not day or total is None:
            continue
        if day < as_of_date or (include_as_of_day and day == as_of_date):
            days.append((day, total, row.get("funds") or []))
    days.sort(key=lambda d: d[0])
    days = days[-look_back_days:]

    header = f"## U.S. spot {base} ETF flows (CryptoETF.today)\n"
    if not days:
        return header + (
            f"\nNO_DATA_AVAILABLE: no {base} ETF flow days before {as_of_date} "
            f"(the free tier covers the last 30 days). Do not estimate ETF flows."
        )

    flows = [f for _, f, _ in days]
    streak = 1
    for previous in reversed(flows[:-1]):
        if (previous >= 0) == (flows[-1] >= 0):
            streak += 1
        else:
            break
    direction = "inflow" if flows[-1] >= 0 else "outflow"

    lines = [
        header,
        f"- Latest day {days[-1][0]}: {_usd_m(flows[-1])} ({streak}-day {direction} streak)",
        f"- Last 5 trading days: {_usd_m(sum(flows[-5:]))}",
        f"- Last {len(flows)} trading days: {_usd_m(sum(flows))}",
        "- Reading: sustained inflows = institutional demand absorbing supply; outflows = redemptions.",
        "",
        "| Day | Net flow | Largest movers |",
        "| --- | --- | --- |",
    ]
    for day, flow, funds in reversed(days[-10:]):
        movers = sorted(
            (f for f in funds if _num(f.get("netFlowUsdM"))),
            key=lambda f: abs(_num(f["netFlowUsdM"])),
            reverse=True,
        )[:TOP_FUNDS]
        mover_text = ", ".join(f"{f.get('ticker')} {_usd_m(_num(f['netFlowUsdM']))}" for f in movers) or "n/a"
        lines.append(f"| {day} | {_usd_m(flow)} | {mover_text} |")
    return "\n".join(lines) + "\n"
