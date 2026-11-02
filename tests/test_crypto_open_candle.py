"""Crypto trades 24/7: a daily candle only closes at 00:00 UTC.

A report run during the UTC day used to treat the live price as that day's
"close" (and could show a close below the session low, because the high/low
and the close came from different moments). The open candle is now kept out
of indicators and quoted separately as the price at report time.
"""
from types import SimpleNamespace

import pandas as pd
import pytest

import tradingagents.dataflows.vendors.yahoo.market as yfin
import tradingagents.dataflows.vendors.yahoo.snapshot as snap
from tradingagents.dataflows.config import set_config
from tradingagents.dataflows.vendors.yahoo import ohlcv

NOW = pd.Timestamp("2026-11-02 18:55")  # 11:55 AM in Denver, UTC day still open


def _frame(dates, closes):
    return pd.DataFrame(
        {"Date": pd.to_datetime(dates), "Open": closes, "High": [c + 50 for c in closes],
         "Low": [c - 50 for c in closes], "Close": closes, "Volume": [1] * len(closes)}
    )


@pytest.mark.unit
def test_candle_open_only_for_crypto_during_its_utc_day():
    assert ohlcv.crypto_candle_is_open("BTC-USD", "2026-11-02", NOW)
    assert not ohlcv.crypto_candle_is_open("BTC-USD", "2026-11-01", NOW)
    # Exactly at 00:00 UTC the candle has closed.
    assert not ohlcv.crypto_candle_is_open("BTC-USD", "2026-11-02", pd.Timestamp("2026-11-03 00:00"))
    # Stocks are untouched.
    assert not ohlcv.crypto_candle_is_open("AAPL", "2026-11-02", NOW)


@pytest.mark.unit
def test_split_open_candle():
    df = _frame(["2026-10-31", "2026-11-01", "2026-11-02"], [100.0, 101.0, 99.0])
    settled, open_row = ohlcv.split_open_crypto_candle(df, "BTC-USD", NOW)
    assert list(settled["Close"]) == [100.0, 101.0]
    assert open_row["Close"] == 99.0
    same, none = ohlcv.split_open_crypto_candle(df, "AAPL", NOW)
    assert len(same) == 3 and none is None


@pytest.mark.unit
def test_load_ohlcv_drops_open_crypto_candle(monkeypatch, tmp_path):
    set_config({"data_cache_dir": str(tmp_path)})
    today = pd.Timestamp.today().normalize()
    utc_today = ohlcv.utc_now_naive().normalize()
    idx = pd.date_range(end=utc_today, periods=5, freq="D")

    def fake_history(start, end, **kwargs):
        return pd.DataFrame(
            {"Open": 1.0, "High": 2.0, "Low": 0.5, "Close": [1.0, 2.0, 3.0, 4.0, 5.0], "Volume": 1},
            index=idx,
        )

    monkeypatch.setattr(ohlcv.yf, "Ticker", lambda symbol: SimpleNamespace(history=fake_history))
    as_of = max(today, utc_today).strftime("%Y-%m-%d")
    data = ohlcv.load_ohlcv("BTC-USD", as_of)
    assert data["Date"].max() < utc_today  # the open UTC-day candle is gone
    kept = ohlcv.load_ohlcv("BTC-USD", as_of, keep_open_candle=True)
    assert kept["Date"].max() == utc_today


@pytest.mark.unit
def test_snapshot_quotes_live_price_separately(monkeypatch):
    dates = pd.date_range(end="2026-11-02", periods=260, freq="D")
    closes = [70000.0 + i * 10 for i in range(260)]
    closes[-1] = 76891.44
    df = _frame(dates, closes)
    monkeypatch.setattr(snap, "load_ohlcv", lambda *a, **k: df.copy())
    monkeypatch.setattr(snap, "utc_now_naive", lambda: NOW)
    out = snap.build_verified_market_snapshot("BTC-USD", "2026-11-02")
    assert "Live price (unfinished candle, NOT a close)" in out
    assert "| Price at report time | 76891.44 |" in out
    assert "| Report time (UTC) | 2026-11-02 18:55 |" in out
    assert "- Latest trading row used: 2026-11-01" in out
    assert "| 2026-11-02 | 76891.44 |" not in out  # not listed among closes


@pytest.mark.unit
def test_raw_crypto_data_flags_open_row(monkeypatch):
    utc_today = ohlcv.utc_now_naive().normalize()

    class FakeTicker:
        def __init__(self, symbol):
            pass

        def history(self, start, end):
            idx = pd.to_datetime([utc_today - pd.Timedelta(days=1), utc_today])
            return pd.DataFrame(
                {"Open": [1.0, 2.0], "High": [1.0, 2.0], "Low": [1.0, 2.0],
                 "Close": [1.0, 2.0], "Volume": [1, 2]},
                index=idx,
            )

    monkeypatch.setattr(yfin.yf, "Ticker", FakeTicker)
    end = utc_today.strftime("%Y-%m-%d")
    start = (utc_today - pd.Timedelta(days=5)).strftime("%Y-%m-%d")
    assert "UNFINISHED candle" in yfin.get_YFin_data_online("BTC-USD", start, end)
    assert "UNFINISHED candle" not in yfin.get_YFin_data_online("AAPL", start, end)
