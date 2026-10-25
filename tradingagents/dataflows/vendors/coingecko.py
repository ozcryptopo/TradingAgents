"""CoinGecko vendor for global crypto market-cap series (TOTAL, TOTAL2, TOTAL3).

TradingView-style TOTAL symbols are not exchange tickers. This vendor maps them
to CoinGecko's global market-cap chart endpoint and returns a CSV series that
the Market Analyst can consume the same way it consumes yfinance OHLCV.

Requires COINGECKO_API_KEY in the environment (Demo or Pro key).
"""

import logging
import os
from datetime import datetime, UTC

import pandas as pd
import requests

from tradingagents.dataflows.errors import NoMarketDataError, VendorUnavailableError

logger = logging.getLogger(__name__)

BASE_URL = "https://api.coingecko.com/api/v3"
REQUEST_TIMEOUT = 30

# TradingView-style symbols -> description (all use the same global chart)
SYMBOL_MAP = {
    "TOTAL": "Total crypto market cap",
    "TOTAL2": "Total crypto market cap excluding BTC",
    "TOTAL3": "Total crypto market cap excluding BTC and ETH",
}


def _headers() -> dict:
    key = os.getenv("COINGECKO_API_KEY", "").strip()
    headers = {"Accept": "application/json"}
    if key:
        headers["x-cg-demo-api-key"] = key
    return headers


def _get_global_chart(days: int = 180) -> dict:
    url = f"{BASE_URL}/global/market_cap_chart"
    params = {"days": days, "vs_currency": "usd"}
    try:
        r = requests.get(url, headers=_headers(), params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"CoinGecko unreachable: {exc}") from None
    if r.status_code == 429 or r.status_code >= 500:
        raise VendorUnavailableError(f"CoinGecko returned {r.status_code}")
    if r.status_code == 401 or r.status_code == 403:
        raise VendorUnavailableError("CoinGecko key rejected or missing")
    r.raise_for_status()
    return r.json()


def get_stock_data(symbol: str, start_date: str, end_date: str) -> str:
    """Return historical market-cap CSV for TOTAL / TOTAL2 / TOTAL3."""
    symbol = symbol.upper().strip()
    if symbol not in SYMBOL_MAP:
        raise NoMarketDataError(
            symbol,
            symbol,
            "not a supported global market-cap symbol (TOTAL, TOTAL2, TOTAL3)",
        )

    try:
        data = _get_global_chart(days=365)
    except VendorUnavailableError:
        raise
    except Exception as exc:
        raise VendorUnavailableError(f"CoinGecko request failed: {exc}") from None

    chart = data.get("market_cap_chart") or {}
    points = chart.get("market_cap") or []
    if not points:
        raise NoMarketDataError(symbol, symbol, "CoinGecko returned an empty market-cap series")

    rows = []
    for ts_ms, value in points:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=UTC).strftime("%Y-%m-%d")
        rows.append({"Date": dt, "Close": value})

    df = pd.DataFrame(rows).drop_duplicates("Date").sort_values("Date")
    df = df[(df["Date"] >= start_date) & (df["Date"] <= end_date)]

    if df.empty:
        raise NoMarketDataError(
            symbol,
            symbol,
            f"no rows between {start_date} and {end_date}",
        )

    # Synthesize OHLC so downstream indicator code has something to work with.
    # Market-cap series is a single value per day; Open/High/Low mirror Close.
    df["Open"] = df["Close"]
    df["High"] = df["Close"]
    df["Low"] = df["Close"]
    df["Volume"] = 0
    df = df[["Date", "Open", "High", "Low", "Close", "Volume"]]

    label = f"{SYMBOL_MAP[symbol]} ({symbol})"
    header = f"# Market-cap data for {label} from {start_date} to {end_date}\n"
    header += f"# Source: CoinGecko global market cap chart\n"
    header += f"# Total records: {len(df)}\n\n"
    return header + df.to_csv(index=False)
