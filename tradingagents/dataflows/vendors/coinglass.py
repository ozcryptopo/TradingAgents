"""CoinGlass spot-ETF flow vendor (needs a CoinGlass API key).

Daily net creations/redemptions for U.S. spot crypto ETFs (IBIT, FBTC, GBTC,
...), the clearest read on institutional demand. Covers Bitcoin, Ethereum,
Solana and XRP ETFs.

Reads ``COINGLASS_API_KEY`` (https://www.coinglass.com/pricing; ETF flow history
is on every paid plan). Without a key the vendor raises
``VendorNotConfiguredError`` and the run carries on without ETF data.

Point in time: a day's flows are known only after that U.S. session closes, so
a historical run sees flows strictly before its date.
"""

import logging
import os
from datetime import UTC, datetime

import requests

from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.errors import VendorNotConfiguredError, VendorUnavailableError
from tradingagents.dataflows.symbols import crypto_base

logger = logging.getLogger(__name__)

API_BASE = "https://open-api-v4.coinglass.com/api/etf"
REQUEST_TIMEOUT = 30
DEFAULT_LOOKBACK_DAYS = 14
TOP_ETFS = 4

# Crypto base -> CoinGlass ETF path segment.
ETF_ASSETS = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "XRP": "xrp"}


class CoinGlassNotConfiguredError(VendorNotConfiguredError):
    """COINGLASS_API_KEY is not set."""


def get_api_key() -> str:
    key = os.getenv("COINGLASS_API_KEY")
    if not key:
        raise CoinGlassNotConfiguredError(
            "COINGLASS_API_KEY is not set, so spot-ETF flows are unavailable. "
            "Add COINGLASS_API_KEY=... to your .env (paid key from coinglass.com/pricing) to enable them."
        )
    return key


def _request(asset: str) -> list:
    key = get_api_key()
    try:
        response = requests.get(
            f"{API_BASE}/{asset}/flow-history",
            headers={"CG-API-KEY": key, "accept": "application/json"},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"CoinGlass unreachable: {str(exc).replace(key, '***')}") from None
    if response.status_code == 429 or response.status_code >= 500:
        raise VendorUnavailableError(f"CoinGlass returned {response.status_code}")
    if response.status_code in (401, 403):
        raise CoinGlassNotConfiguredError(
            f"CoinGlass rejected the API key ({response.status_code}); check COINGLASS_API_KEY and your plan."
        )
    response.raise_for_status()
    payload = response.json()
    if str(payload.get("code")) != "0":
        raise VendorUnavailableError(f"CoinGlass error: {payload.get('msg') or payload.get('code')}")
    return payload.get("data") or []


def _usd(value: float) -> str:
    sign = "+" if value >= 0 else "-"
    value = abs(value)
    if value >= 1e9:
        return f"{sign}${value / 1e9:,.2f}B"
    if value >= 1e6:
        return f"{sign}${value / 1e6:,.1f}M"
    return f"{sign}${value:,.0f}"


def get_etf_flows(symbol: str, as_of_date: str, look_back_days: int | None = None) -> str:
    """Daily U.S. spot-ETF net flows for a crypto pair, as markdown."""
    base = crypto_base(symbol)
    if not base:
        return f"ETF FLOWS NOT APPLICABLE: '{symbol}' is not a recognised USD-quoted crypto pair."
    asset = ETF_ASSETS.get(base)
    if not asset:
        return (
            f"ETF FLOWS NOT AVAILABLE: no U.S. spot-ETF flow series is tracked for {base} "
            f"(covered: {', '.join(ETF_ASSETS)}). Do not estimate ETF flows."
        )
    look_back_days = look_back_days or DEFAULT_LOOKBACK_DAYS

    include_as_of_day = not is_historical(as_of_date)
    days = []
    for row in _request(asset):
        try:
            day = datetime.fromtimestamp(int(row["timestamp"]) / 1000, UTC).strftime("%Y-%m-%d")
            flow = float(row.get("flow_usd") or 0)
        except (KeyError, TypeError, ValueError):
            continue
        if day < as_of_date or (include_as_of_day and day == as_of_date):
            days.append((day, flow, row))
    days.sort(key=lambda d: d[0])
    days = days[-look_back_days:]

    header = f"## U.S. spot {base} ETF flows (CoinGlass)\n"
    if not days:
        return header + (
            f"\nNO_DATA_AVAILABLE: CoinGlass returned no {base} ETF flow days before {as_of_date}. "
            f"Do not estimate ETF flows."
        )

    flows = [f for _, f, _ in days]

    def total(n: int) -> float:
        return sum(flows[-n:])

    streak = 1
    for previous in reversed(flows[:-1]):
        if (previous >= 0) == (flows[-1] >= 0):
            streak += 1
        else:
            break
    direction = "inflow" if flows[-1] >= 0 else "outflow"

    lines = [
        header,
        f"- Latest day {days[-1][0]}: {_usd(flows[-1])} ({streak}-day {direction} streak)",
        f"- Last 5 trading days: {_usd(total(5))}",
        f"- Last {len(flows)} trading days: {_usd(total(len(flows)))}",
        "- Reading: sustained inflows = institutional demand absorbing supply; outflows = redemptions.",
        "",
        "| Day | Net flow | Largest movers |",
        "| --- | --- | --- |",
    ]
    for day, flow, row in reversed(days[-10:]):
        movers = sorted(
            (e for e in row.get("etf_flows") or [] if e.get("flow_usd")),
            key=lambda e: abs(float(e["flow_usd"])),
            reverse=True,
        )[:TOP_ETFS]
        mover_text = ", ".join(f"{e.get('etf_ticker')} {_usd(float(e['flow_usd']))}" for e in movers) or "n/a"
        lines.append(f"| {day} | {_usd(flow)} | {mover_text} |")
    return "\n".join(lines) + "\n"
