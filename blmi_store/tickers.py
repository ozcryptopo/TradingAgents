"""Check that a symbol is real before anyone pays for a report on it."""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from tradingagents.dataflows.symbols import crypto_base, normalize_symbol

_SHAPE = re.compile(r"^[A-Za-z0-9.\-=^+/]{1,20}$")
_cache: dict[str, tuple[float, dict]] = {}
CACHE_SECONDS = 3600


def asset_type_of(symbol: str) -> str:
    return "crypto" if crypto_base(symbol) else "stock"


def analysis_date(asset_type: str, when: datetime | None = None) -> str:
    """The date a report is run for: the UTC day for crypto, the New York trading day for stocks."""
    when = when or datetime.now(timezone.utc)
    if asset_type == "crypto":
        return when.astimezone(timezone.utc).strftime("%Y-%m-%d")
    return when.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


def _fetch(symbol: str) -> dict:
    import yfinance as yf

    t = yf.Ticker(symbol)
    hist = t.history(period="1mo")
    if hist is None or hist.empty:
        return {"ok": False, "error": f"No recent market data found for {symbol}."}
    name = symbol
    try:
        info = t.get_info() or {}
        name = info.get("shortName") or info.get("longName") or symbol
    except Exception:  # noqa: BLE001 - the name is a nicety; the price data is what matters
        pass
    return {"ok": True, "symbol": symbol, "name": name, "last": round(float(hist["Close"].iloc[-1]), 4)}


def validate(raw: str, fetch=_fetch) -> dict:
    """{"ok": True, "symbol", "name", "asset_type"} or {"ok": False, "error"}."""
    raw = (raw or "").strip()
    if not _SHAPE.match(raw):
        return {"ok": False, "error": "Enter a stock or crypto symbol, like AAPL, SPY or BTC-USD."}
    symbol = normalize_symbol(raw.upper())
    hit = _cache.get(symbol)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    try:
        result = fetch(symbol)
    except Exception:  # noqa: BLE001
        return {"ok": False, "error": "Market data is unavailable right now. Please try again in a minute."}
    if result.get("ok"):
        result["asset_type"] = asset_type_of(symbol)
        _cache[symbol] = (time.time(), result)
    return result
