"""Backtest of the gold/Dow divergence + RSI pop strategy.

Mirrors gold_dow_divergence.pine. Works on any bar size: 1-second data
(the size the strategy is meant for) or 1-minute data (a rough stand-in).

Data sources:
  --source yahoo        free 1-minute GC=F / YM=F, last ~7 days
  --gold a.csv --dow b.csv   your own bars: columns timestamp,open,high,low,close
                             (timestamp in UTC or with a timezone offset)

Example:
  python backtest.py --source yahoo
  python backtest.py --gold gc_1s.csv --dow ym_1s.csv --rr 2
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

NY = "America/New_York"


@dataclass
class Params:
    lookback_sec: int = 120        # divergence window
    min_gold_move: float = 0.03    # % gold must move over the window
    dow_flat_tol: float = 0.01     # % the Dow may move "with" gold and still count as flat
    min_spread: float = 0.04       # % gap between the two moves
    rsi_len: int = 5
    pop_bars: int = 3              # pop must happen within this many bars
    pop_size: float = 15.0         # RSI points
    pop_vs_avg: float = 3.0        # pop vs average one-bar RSI move (0 = off)
    stop_mode: str = "pop"         # "pop" (beyond pop low/high) or "fixed"
    fixed_ticks: int = 20
    min_ticks: int = 5
    buf_ticks: int = 2
    rr: float = 1.0
    max_hold_sec: int = 600
    cooldown_sec: int = 60
    max_trades: int = 5
    max_day_loss: float = 300.0
    session_start: str = "09:00"
    session_end: str = "11:00"
    # Contract: micro gold (MGC). Tick 0.10 = $1.
    tick: float = 0.10
    point_value: float = 10.0      # $ per 1.00 move per contract
    commission: float = 0.85       # $ per contract per side
    slippage_ticks: int = 1        # per side, on market entries and stop exits


# ---------------------------------------------------------------- data
def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.lower() for c in df.columns]
    ts = pd.to_datetime(df.pop("timestamp"), utc=True)
    df.index = ts.dt.tz_convert(NY)
    return df[["open", "high", "low", "close"]].astype(float).sort_index()


def load_yahoo(symbol: str) -> pd.DataFrame:
    import yfinance as yf

    df = yf.download(symbol, period="7d", interval="1m", progress=False, auto_adjust=False)
    if df.empty:
        raise SystemExit(f"No data returned for {symbol}")
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.columns = [c.lower() for c in df.columns]
    df.index = df.index.tz_convert(NY)
    return df[["open", "high", "low", "close"]].astype(float)


def bar_seconds(idx: pd.DatetimeIndex) -> int:
    return int(pd.Series(idx).diff().dt.total_seconds().mode().iloc[0])


# ---------------------------------------------------------------- signals
def rsi(close: pd.Series, length: int) -> pd.Series:
    """Wilder's RSI, same as TradingView's ta.rsi."""
    delta = close.diff()
    up = delta.clip(lower=0).ewm(alpha=1 / length, adjust=False).mean()
    down = (-delta.clip(upper=0)).ewm(alpha=1 / length, adjust=False).mean()
    rs = up / down
    out = 100 - 100 / (1 + rs)
    return out.where(down != 0, 100.0)


def build_signals(gold: pd.DataFrame, dow_close: pd.Series, p: Params, bar_sec: int) -> pd.DataFrame:
    n = max(1, round(p.lookback_sec / bar_sec))
    df = gold.copy()
    df["dow"] = dow_close.reindex(df.index).ffill()

    df["gold_chg"] = (df.close / df.close.shift(n) - 1) * 100
    df["dow_chg"] = (df.dow / df.dow.shift(n) - 1) * 100
    long_div = (df.gold_chg >= p.min_gold_move) & (df.dow_chg <= p.dow_flat_tol) & (
        df.gold_chg - df.dow_chg >= p.min_spread
    )
    short_div = (df.gold_chg <= -p.min_gold_move) & (df.dow_chg >= -p.dow_flat_tol) & (
        df.dow_chg - df.gold_chg >= p.min_spread
    )

    r = rsi(df.close, p.rsi_len)
    avg_move = r.diff().abs().rolling(30).mean()
    w = p.pop_bars + 1
    drop = r.rolling(w).max() - r
    rise = r - r.rolling(w).min()
    ref = avg_move.shift(p.pop_bars + 1)
    rel_drop = (p.pop_vs_avg == 0) | (drop >= p.pop_vs_avg * ref)
    rel_rise = (p.pop_vs_avg == 0) | (rise >= p.pop_vs_avg * ref)
    long_pop = (drop >= p.pop_size) & rel_drop
    short_pop = (rise >= p.pop_size) & rel_rise

    df["long_sig"] = long_pop & ~long_pop.shift(1, fill_value=False) & (
        long_div | long_div.shift(p.pop_bars, fill_value=False)
    )
    df["short_sig"] = short_pop & ~short_pop.shift(1, fill_value=False) & (
        short_div | short_div.shift(p.pop_bars, fill_value=False)
    )
    df["pop_low"] = df.low.rolling(w).min()
    df["pop_high"] = df.high.rolling(w).max()
    df["rsi"] = r
    t = df.index.strftime("%H:%M")
    df["in_session"] = (t >= p.session_start) & (t < p.session_end)
    return df


# ---------------------------------------------------------------- simulation
def simulate(df: pd.DataFrame, p: Params, bar_sec: int) -> pd.DataFrame:
    hold_bars = max(1, round(p.max_hold_sec / bar_sec)) if p.max_hold_sec else None
    cool_bars = round(p.cooldown_sec / bar_sec)
    slip = p.slippage_ticks * p.tick

    o, h, l, c = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    long_sig, short_sig = df.long_sig.to_numpy(), df.short_sig.to_numpy()
    pop_low, pop_high = df.pop_low.to_numpy(), df.pop_high.to_numpy()
    in_sess = df.in_session.to_numpy()
    days = df.index.date
    idx = df.index

    trades = []
    pos = None              # dict while in a trade
    pending = None          # signal waiting for next bar's open
    last_exit = -10**9
    day, day_trades, day_pnl = None, 0, 0.0

    def close_trade(i, price, reason):
        nonlocal pos, last_exit, day_pnl
        d = pos["dir"]
        pnl = (price - pos["entry"]) * d * p.point_value - 2 * p.commission
        trades.append({
            "entry_time": idx[pos["i"]], "exit_time": idx[i], "direction": "long" if d == 1 else "short",
            "entry": pos["entry"], "stop": pos["stop"], "target": pos["target"], "exit": price,
            "reason": reason, "pnl": round(pnl, 2), "bars_held": i - pos["i"],
        })
        day_pnl += pnl
        last_exit = i
        pos = None

    for i in range(len(df)):
        if days[i] != day:
            day, day_trades, day_pnl = days[i], 0, 0.0

        # 1. fill a pending entry at this bar's open
        if pending is not None and pos is None:
            d, ticks = pending
            entry = o[i] + slip * d
            dist = ticks * p.tick
            pos = {"i": i, "dir": d, "entry": entry,
                   "stop": entry - dist * d, "target": entry + dist * p.rr * d}
            day_trades += 1
        pending = None

        # 2. manage open trade inside this bar (stop checked first: conservative)
        if pos is not None:
            d = pos["dir"]
            hit_stop = l[i] <= pos["stop"] if d == 1 else h[i] >= pos["stop"]
            hit_tgt = h[i] >= pos["target"] if d == 1 else l[i] <= pos["target"]
            if hit_stop:
                close_trade(i, pos["stop"] - slip * d, "stop")
            elif hit_tgt:
                close_trade(i, pos["target"], "target")
            elif not in_sess[i]:
                close_trade(i, c[i] - slip * d, "session end")
            elif hold_bars and i - pos["i"] >= hold_bars:
                close_trade(i, c[i] - slip * d, "time stop")
            elif day_pnl + (c[i] - pos["entry"]) * d * p.point_value <= -p.max_day_loss:
                close_trade(i, c[i] - slip * d, "daily loss")

        # 3. new signal on this bar's close -> enter next bar
        can = (pos is None and in_sess[i] and i - last_exit >= cool_bars
               and day_trades < p.max_trades and day_pnl > -p.max_day_loss)
        if can and long_sig[i] != short_sig[i]:
            d = 1 if long_sig[i] else -1
            if p.stop_mode == "fixed":
                dist = p.fixed_ticks * p.tick
            elif d == 1:
                dist = c[i] - (pop_low[i] - p.buf_ticks * p.tick)
            else:
                dist = (pop_high[i] + p.buf_ticks * p.tick) - c[i]
            ticks = max(round(dist / p.tick), p.min_ticks)
            pending = (d, ticks)

    return pd.DataFrame(trades)


def summarize(trades: pd.DataFrame) -> dict:
    if trades.empty:
        return {"trades": 0}
    wins = trades[trades.pnl > 0]
    losses = trades[trades.pnl <= 0]
    gross_win, gross_loss = wins.pnl.sum(), -losses.pnl.sum()
    equity = trades.pnl.cumsum()
    return {
        "trades": len(trades),
        "win_rate_%": round(100 * len(wins) / len(trades), 1),
        "net_pnl_$": round(trades.pnl.sum(), 2),
        "avg_win_$": round(wins.pnl.mean(), 2) if len(wins) else 0.0,
        "avg_loss_$": round(losses.pnl.mean(), 2) if len(losses) else 0.0,
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else float("inf"),
        "max_drawdown_$": round((equity - equity.cummax()).min(), 2),
        "exits": trades.reason.value_counts().to_dict(),
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", choices=["yahoo", "csv"], default="csv")
    ap.add_argument("--gold"), ap.add_argument("--dow")
    ap.add_argument("--rr", type=float, default=1.0)
    ap.add_argument("--session", default="09:00-11:00", help="NY time, e.g. 09:00-11:00 or 00:00-23:59")
    ap.add_argument("--out", default="trades.csv")
    args = ap.parse_args()

    if args.source == "yahoo":
        gold, dow = load_yahoo("GC=F"), load_yahoo("YM=F")
    else:
        if not (args.gold and args.dow):
            ap.error("--gold and --dow CSV files are required with --source csv")
        gold, dow = load_csv(args.gold), load_csv(args.dow)

    start, end = args.session.split("-")
    p = Params(rr=args.rr, session_start=start, session_end=end)
    bs = bar_seconds(gold.index)
    if bs > 1:
        print(f"NOTE: {bs}-second bars. The strategy is designed for 1-second bars; "
              "treat these results as a rough check only.\n")

    df = build_signals(gold, dow.close, p, bs)
    trades = simulate(df, p, bs)
    print(f"Data: {gold.index.min()} -> {gold.index.max()}  ({len(gold):,} bars)")
    print("Settings:", {k: v for k, v in asdict(p).items() if k in ("rr", "session_start", "session_end")})
    for k, v in summarize(trades).items():
        print(f"  {k:16} {v}")
    if not trades.empty:
        trades.to_csv(args.out, index=False)
        print(f"\nTrade list saved to {args.out}")


if __name__ == "__main__":
    main()
