"""Facts computed straight from price data, with no AI involved.

The cover tiles come from here, the editing agent is given them as ground
truth, and the quality-control agent checks the written report against them.
"""

from __future__ import annotations

from stockstats import wrap

from tradingagents.dataflows.vendors.yahoo.ohlcv import load_ohlcv, split_open_crypto_candle, utc_now_naive


def compute(ticker: str, analysis_date: str, asset_type: str, loader=load_ohlcv, now_utc=None) -> dict:
    now_utc = now_utc or utc_now_naive()
    raw = loader(ticker, analysis_date, fill_gaps=False, keep_open_candle=True)
    raw = raw.dropna(subset=["Close"])
    settled, open_row = split_open_crypto_candle(raw, ticker, now_utc) if asset_type == "crypto" else (raw, None)
    if settled.empty:
        raise ValueError(f"No closed daily data for {ticker}")
    stats = wrap(settled.copy())
    last = settled.iloc[-1]
    close = float(last["Close"])
    facts = {
        "ticker": ticker,
        "asset_type": asset_type,
        "analysis_date": analysis_date,
        "last_close": close,
        "last_close_date": str(last["Date"].date()),
        "sma_50": _val(stats, "close_50_sma"),
        "sma_200": _val(stats, "close_200_sma"),
        "ema_10": _val(stats, "close_10_ema"),
        "rsi_14": _val(stats, "rsi"),
        "macd": _val(stats, "macd"),
        "macd_hist": _val(stats, "macdh"),
        "rows": len(settled),
    }
    if open_row is not None:
        facts.update(live_price=float(open_row["Close"]), live_time_utc=now_utc.strftime("%Y-%m-%d %H:%M"),
                     open_candle_date=str(open_row["Date"].date()))
    ref = facts.get("live_price", close)
    facts["reference_price"] = ref
    if facts["sma_200"] and len(settled) >= 200:
        pct = (ref / facts["sma_200"] - 1) * 100
        facts["vs_sma_200_pct"] = round(pct, 2)
        facts["trend_value"] = f"{'Above' if pct >= 0 else 'Below'} 200-day average"
        facts["trend_note"] = f"Price {abs(pct):.1f}% {'above' if pct >= 0 else 'below'} the 200-day average of {_money(facts['sma_200'])}"
    else:
        facts["trend_value"] = "Not enough history"
        facts["trend_note"] = "Fewer than 200 days of price data"
    return facts


def _val(stats, name):
    try:
        v = stats[name].iloc[-1]
        return None if v != v else round(float(v), 4)  # NaN check
    except Exception:  # noqa: BLE001
        return None


def _money(v: float) -> str:
    return f"${v:,.2f}" if v >= 1 else f"${v:,.6f}"


def report_notes(facts: dict, gaps: list[str], summary: str) -> dict:
    """The ``report_notes`` the educational PDF edition reads."""
    if "live_price" in facts:
        price_label, price_value = "Price at report time", _money(facts["live_price"])
        price_note = f"{facts['live_time_utc']} UTC · intraday, not a daily close"
        timing = (f"Crypto trades 24 hours a day, 7 days a week. By convention a daily close is the price at 00:00 UTC "
                  f"and a weekly close is Sunday at 00:00 UTC. This report was produced at {facts['live_time_utc']} UTC, "
                  f"before the {facts['open_candle_date']} daily candle closed. The price shown is the price at report "
                  f"time; indicators use completed daily candles through {facts['last_close_date']}.")
    else:
        price_label = "Last close"
        price_value = _money(facts["last_close"])
        price_note = facts["last_close_date"]
        timing = (f"Prices and indicators use completed daily sessions through {facts['last_close_date']}."
                  if facts["asset_type"] == "stock" else "")
    return {
        "price_label": price_label, "price_value": price_value, "price_note": price_note,
        "trend_label": "Long-term trend", "trend_value": facts["trend_value"], "trend_note": facts["trend_note"],
        "timing_note": timing, "gaps": gaps, "summary": summary,
    }


def facts_text(facts: dict) -> str:
    """The facts as plain text for the editing and quality-control agents."""
    lines = [f"Ticker: {facts['ticker']} ({facts['asset_type']}); analysis date {facts['analysis_date']}.",
             f"Last completed daily close: {facts['last_close']} on {facts['last_close_date']}."]
    if "live_price" in facts:
        lines.append(f"Price at report time (intraday, NOT a close): {facts['live_price']} at {facts['live_time_utc']} UTC.")
    for key, label in (("sma_200", "200-day simple moving average"), ("sma_50", "50-day simple moving average"),
                       ("ema_10", "10-day exponential moving average"), ("rsi_14", "RSI (14)"),
                       ("macd", "MACD line"), ("macd_hist", "MACD histogram")):
        if facts.get(key) is not None:
            lines.append(f"{label}: {facts[key]}")
    if facts.get("vs_sma_200_pct") is not None:
        lines.append(f"Reference price vs 200-day average: {facts['vs_sma_200_pct']}%")
    return "\n".join(lines)
