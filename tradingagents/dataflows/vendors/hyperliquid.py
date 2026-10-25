"""Hyperliquid perpetual-futures vendor: funding rates and open interest (no key).

Funding shows how crowded leveraged positioning is: a persistently positive
rate means longs pay shorts to hold (crowded long, squeeze risk to the
downside); negative means the reverse. Open interest shows how much leverage is
in the market.

Uses Hyperliquid's public info endpoint (https://api.hyperliquid.xyz/info, POST,
no key). Hyperliquid is a single on-chain venue, so its figures are a sample of
crypto derivatives positioning, not the whole market. It funds hourly.

Point in time: funding history is cut at the analysis date. Open interest and
the live funding rate exist only as a current snapshot, so a historical run
withholds them.
"""

import logging
from datetime import UTC, datetime, timedelta

import requests

from tradingagents.dataflows.date_window import is_historical
from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.symbols import crypto_base

logger = logging.getLogger(__name__)

INFO_URL = "https://api.hyperliquid.xyz/info"
REQUEST_TIMEOUT = 30
DEFAULT_LOOKBACK_DAYS = 14
HOURS_PER_YEAR = 24 * 365


def _post(body: dict):
    try:
        response = requests.post(INFO_URL, json=body, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"Hyperliquid unreachable: {exc}") from None
    if response.status_code == 429 or response.status_code >= 500:
        raise VendorUnavailableError(f"Hyperliquid returned {response.status_code}")
    response.raise_for_status()
    return response.json()


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _rate(hourly: float | None) -> str:
    """An hourly funding rate as % per hour and annualized %."""
    if hourly is None:
        return "n/a"
    return f"{hourly * 100:+.4f}%/h ({hourly * HOURS_PER_YEAR * 100:+.1f}% annualized)"


def _usd(value: float | None) -> str:
    if value is None:
        return "n/a"
    if abs(value) >= 1e9:
        return f"${value / 1e9:,.2f}B"
    if abs(value) >= 1e6:
        return f"${value / 1e6:,.1f}M"
    return f"${value:,.0f}"


def _live_snapshot(coin: str) -> list[str]:
    meta, contexts = _post({"type": "metaAndAssetCtxs"})
    names = [asset.get("name") for asset in meta.get("universe", [])]
    if coin not in names:
        return [f"- {coin} has no Hyperliquid perpetual; no live snapshot."]
    ctx = contexts[names.index(coin)]
    oracle = _num(ctx.get("oraclePx"))
    mark = _num(ctx.get("markPx"))
    open_interest = _num(ctx.get("openInterest"))
    prev = _num(ctx.get("prevDayPx"))
    lines = [
        f"- Current funding: {_rate(_num(ctx.get('funding')))}",
        f"- Open interest: {open_interest:,.2f} {coin} (~{_usd(open_interest * oracle if open_interest and oracle else None)})"
        if open_interest is not None else "- Open interest: n/a",
        f"- 24h notional volume: {_usd(_num(ctx.get('dayNtlVlm')))}",
    ]
    if mark and oracle:
        lines.append(f"- Mark vs oracle (spot index): {(mark - oracle) / oracle * 100:+.3f}% (premium > 0 = perp trades rich)")
    if oracle and prev:
        price = f"{oracle:,.2f}" if oracle >= 1 else f"{oracle:.6g}"
        lines.append(f"- Oracle price {price}, 24h change {(oracle - prev) / prev * 100:+.2f}%")
    return lines


def get_derivatives_data(symbol: str, as_of_date: str, look_back_days: int | None = None) -> str:
    """Perpetual funding history and (on a live run) open interest, as markdown."""
    coin = crypto_base(symbol)
    if not coin:
        return (
            f"DERIVATIVES DATA NOT APPLICABLE: '{symbol}' is not a recognised USD-quoted "
            f"crypto pair."
        )
    look_back_days = look_back_days or DEFAULT_LOOKBACK_DAYS
    historical = is_historical(as_of_date)
    end = (
        datetime.strptime(as_of_date, "%Y-%m-%d").replace(tzinfo=UTC)
        if historical
        else datetime.now(UTC)
    )
    start = end - timedelta(days=look_back_days)

    history = _post(
        {
            "type": "fundingHistory",
            "coin": coin,
            "startTime": int(start.timestamp() * 1000),
            "endTime": int(end.timestamp() * 1000),
        }
    ) or []
    points = sorted(
        ((int(h["time"]), _num(h.get("fundingRate"))) for h in history if _num(h.get("fundingRate")) is not None),
        key=lambda p: p[0],
    )

    lines = [
        f"## Perpetual futures positioning: {coin} (Hyperliquid)",
        f"- Window: {start:%Y-%m-%d %H:%M} to {end:%Y-%m-%d %H:%M} UTC; hourly funding",
        "- Single venue: a sample of leveraged positioning, not the whole market.",
        "",
    ]

    if historical:
        lines.append("Live open interest is withheld: this run is dated in the past and Hyperliquid serves OI only as a live snapshot.")
    else:
        lines.append("### Live snapshot")
        lines.extend(_live_snapshot(coin))

    if not points:
        lines.append(
            f"\nNO_DATA_AVAILABLE: no Hyperliquid funding history for {coin} in this window. "
            f"Do not estimate funding rates."
        )
        return "\n".join(lines) + "\n"

    def average(hours: int) -> float | None:
        cutoff = points[-1][0] - hours * 3600 * 1000
        window = [r for t, r in points if t > cutoff]
        return sum(window) / len(window) if window else None

    rates = [r for _, r in points]
    positive_share = sum(1 for r in rates if r > 0) / len(rates) * 100
    lines += [
        "",
        "### Funding rate history",
        f"- Latest settled: {_rate(rates[-1])}",
        f"- 24h average: {_rate(average(24))}",
        f"- 7d average: {_rate(average(24 * 7))}",
        f"- {look_back_days}d average: {_rate(sum(rates) / len(rates))}",
        f"- Hours with positive funding: {positive_share:.0f}% of {len(rates)}",
        "- Reading: sustained positive funding = longs crowded (downside squeeze risk); "
        "negative = shorts crowded (upside squeeze risk); near zero = balanced.",
        "",
        "| Day (UTC) | Average hourly funding | Annualized |",
        "| --- | --- | --- |",
    ]
    by_day: dict[str, list[float]] = {}
    for t, r in points:
        by_day.setdefault(datetime.fromtimestamp(t / 1000, UTC).strftime("%Y-%m-%d"), []).append(r)
    for day in sorted(by_day)[-7:]:
        avg = sum(by_day[day]) / len(by_day[day])
        lines.append(f"| {day} | {avg * 100:+.4f}% | {avg * HOURS_PER_YEAR * 100:+.1f}% |")
    return "\n".join(lines) + "\n"
