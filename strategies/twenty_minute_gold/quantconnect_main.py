# QuantConnect (LEAN) version of the gold/Dow divergence + RSI pop strategy.
# Paste into main.py of a new Python project at quantconnect.com and click Backtest.
#
# Rules (same as gold_dow_divergence.pine / backtest.py):
#   1. Over the last ~2 minutes, micro gold futures move apart from Dow futures:
#      gold up while the Dow is flat/down -> look to BUY; gold down while the Dow
#      is flat/up -> look to SELL.
#   2. Wait for a sharp RSI "pop" AGAINST that direction.
#   3. Enter at market; stop beyond the pop's low/high, target at reward:risk.
#
# Every setting below can be changed in the project's Parameters panel.

from AlgorithmImports import *
from collections import deque
from datetime import time as dtime, timedelta


class GoldDowDivergence(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2025, 9, 1)
        self.set_end_date(2025, 10, 31)
        self.set_cash(10000)
        self.set_time_zone(TimeZones.NEW_YORK)

        # ---- settings ----
        self.lookback_sec = self.get_parameter("lookback_sec", 120)
        self.min_gold_move = self.get_parameter("min_gold_move", 0.03)   # %
        self.dow_flat_tol = self.get_parameter("dow_flat_tol", 0.01)     # %
        self.min_spread = self.get_parameter("min_spread", 0.04)         # %
        self.rsi_len = self.get_parameter("rsi_len", 5)
        self.pop_bars = self.get_parameter("pop_bars", 3)
        self.pop_size = self.get_parameter("pop_size", 15.0)
        self.pop_vs_avg = self.get_parameter("pop_vs_avg", 3.0)
        self.min_ticks = self.get_parameter("min_ticks", 5)
        self.buf_ticks = self.get_parameter("buf_ticks", 2)
        self.rr = self.get_parameter("rr", 1.0)
        self.max_hold_sec = self.get_parameter("max_hold_sec", 600)
        self.cooldown_sec = self.get_parameter("cooldown_sec", 60)
        self.max_trades = self.get_parameter("max_trades", 5)
        self.max_day_loss = self.get_parameter("max_day_loss", 300.0)
        self.qty = self.get_parameter("contracts", 1)
        self.session_start = dtime(*map(int, self.get_parameter("session_start", "09:00").split(":")))
        self.session_end = dtime(*map(int, self.get_parameter("session_end", "11:00").split(":")))
        gold_ticker = self.get_parameter("gold_ticker", "MGC")  # MGC = micro gold, GC = full size

        # ---- data: continuous front-month contracts, 1-second bars ----
        common = dict(extended_market_hours=True,
                      data_mapping_mode=DataMappingMode.OPEN_INTEREST,
                      data_normalization_mode=DataNormalizationMode.RAW,
                      contract_depth_offset=0)
        self.gold = self.add_future(gold_ticker, Resolution.SECOND, **common)
        self.dow = self.add_future("YM", Resolution.SECOND, **common)
        self.tick = self.gold.symbol_properties.minimum_price_variation

        # Indicators only need to warm up shortly before the session
        start_dt = datetime.combine(datetime(2000, 1, 1), self.session_start)
        self.window_start = (start_dt - timedelta(seconds=self.lookback_sec + 300)).time()

        self.dow_last = None
        self.active = False
        self.trade = None
        self.entry_ticket = self.stop_ticket = self.target_ticket = None
        self.pending = None
        self.last_exit = None
        self.day = None
        self.trades_today = 0
        self.day_start_equity = self.portfolio.total_portfolio_value
        self.results = []

    # ------------------------------------------------------------ state
    def reset_state(self):
        n = self.lookback_sec + 1
        self.closes, self.dows = deque(maxlen=n), deque(maxlen=n)
        w = self.pop_bars + 1
        self.rsis, self.highs, self.lows = deque(maxlen=w), deque(maxlen=w), deque(maxlen=w)
        self.abs_moves = deque(maxlen=30)
        self.avg_hist = deque(maxlen=self.pop_bars + 2)
        self.long_div_hist, self.short_div_hist = deque(maxlen=w), deque(maxlen=w)
        self.prev_close = self.avg_up = self.avg_dn = None
        self.prev_long_pop = self.prev_short_pop = False

    def on_securities_changed(self, changes):
        # ~1 tick of slippage on gold market and stop orders
        for s in changes.added_securities:
            s.set_slippage_model(ConstantSlippageModel(0.00003))

    # ------------------------------------------------------------ data
    def on_data(self, data: Slice):
        dbar = data.bars.get(self.dow.symbol)
        if dbar is not None:
            self.dow_last = dbar.close
        gbar = data.bars.get(self.gold.symbol)
        if gbar is None or self.dow_last is None:
            return

        now = self.time
        if now.date() != self.day:
            self.day = now.date()
            self.trades_today = 0
            self.day_start_equity = self.portfolio.total_portfolio_value

        t = now.time()
        in_session = self.session_start <= t < self.session_end

        # manage an open trade
        if self.trade is not None:
            held = (now - self.trade["time"]).total_seconds()
            down_today = self.portfolio.total_portfolio_value - self.day_start_equity
            if not in_session:
                self.exit_trade("session end")
            elif self.max_hold_sec and held >= self.max_hold_sec:
                self.exit_trade("time stop")
            elif down_today <= -self.max_day_loss:
                self.exit_trade("daily loss")

        # only compute signals in the warm-up + session window
        if not (self.window_start <= t < self.session_end):
            self.active = False
            return
        if not self.active:
            self.reset_state()
            self.active = True

        signal = self.update_signals(gbar)
        if signal == 0 or not in_session or self.trade is not None or self.pending is not None:
            return
        if self.trades_today >= self.max_trades:
            return
        if self.portfolio.total_portfolio_value - self.day_start_equity <= -self.max_day_loss:
            return
        if self.last_exit and (now - self.last_exit).total_seconds() < self.cooldown_sec:
            return

        c = gbar.close
        dist = c - (min(self.lows) - self.buf_ticks * self.tick) if signal == 1 \
            else (max(self.highs) + self.buf_ticks * self.tick) - c
        ticks = max(round(dist / self.tick), self.min_ticks)
        self.pending = {"dir": signal, "ticks": ticks}
        self.trades_today += 1
        self.entry_ticket = self.market_order(self.gold.mapped, signal * self.qty,
                                              tag="buy" if signal == 1 else "sell")

    def update_signals(self, bar) -> int:
        c = bar.close
        self.closes.append(c)
        self.dows.append(self.dow_last)
        self.highs.append(bar.high)
        self.lows.append(bar.low)

        # Wilder RSI (same as TradingView ta.rsi)
        if self.prev_close is None:
            self.prev_close = c
            return 0
        delta = c - self.prev_close
        self.prev_close = c
        up, dn = max(delta, 0.0), max(-delta, 0.0)
        a = 1.0 / self.rsi_len
        self.avg_up = up if self.avg_up is None else self.avg_up + a * (up - self.avg_up)
        self.avg_dn = dn if self.avg_dn is None else self.avg_dn + a * (dn - self.avg_dn)
        rsi = 100.0 if self.avg_dn == 0 else 100 - 100 / (1 + self.avg_up / self.avg_dn)

        if self.rsis:
            self.abs_moves.append(abs(rsi - self.rsis[-1]))
        self.rsis.append(rsi)
        avg = sum(self.abs_moves) / len(self.abs_moves) if len(self.abs_moves) == 30 else None
        self.avg_hist.append(avg)

        # divergence
        long_div = short_div = False
        if len(self.closes) == self.closes.maxlen:
            g = (c / self.closes[0] - 1) * 100
            d = (self.dow_last / self.dows[0] - 1) * 100
            long_div = g >= self.min_gold_move and d <= self.dow_flat_tol and g - d >= self.min_spread
            short_div = g <= -self.min_gold_move and d >= -self.dow_flat_tol and d - g >= self.min_spread
        self.long_div_hist.append(long_div)
        self.short_div_hist.append(short_div)

        # RSI pop
        if len(self.rsis) < self.rsis.maxlen or len(self.avg_hist) < self.avg_hist.maxlen \
                or self.avg_hist[0] is None:
            return 0
        ref = self.avg_hist[0]
        drop, rise = max(self.rsis) - rsi, rsi - min(self.rsis)
        long_pop = drop >= self.pop_size and (self.pop_vs_avg == 0 or drop >= self.pop_vs_avg * ref)
        short_pop = rise >= self.pop_size and (self.pop_vs_avg == 0 or rise >= self.pop_vs_avg * ref)

        long_sig = long_pop and not self.prev_long_pop and (long_div or self.long_div_hist[0])
        short_sig = short_pop and not self.prev_short_pop and (short_div or self.short_div_hist[0])
        self.prev_long_pop, self.prev_short_pop = long_pop, short_pop
        if long_sig == short_sig:
            return 0
        return 1 if long_sig else -1

    # ------------------------------------------------------------ orders
    def on_order_event(self, e: OrderEvent):
        if e.status != OrderStatus.FILLED:
            return
        if self.entry_ticket and e.order_id == self.entry_ticket.order_id and self.pending:
            d, ticks = self.pending["dir"], self.pending["ticks"]
            self.pending = None
            dist = ticks * self.tick
            stop = self.round_tick(e.fill_price - d * dist)
            target = self.round_tick(e.fill_price + d * dist * self.rr)
            self.trade = {"dir": d, "symbol": e.symbol, "entry": e.fill_price, "time": self.time,
                          "equity": self.portfolio.total_portfolio_value}
            self.stop_ticket = self.stop_market_order(e.symbol, -d * self.qty, stop, tag="stop")
            self.target_ticket = self.limit_order(e.symbol, -d * self.qty, target, tag="target")
        elif self.trade and self.stop_ticket and e.order_id == self.stop_ticket.order_id:
            self.target_ticket.cancel()
            self.record("stop")
        elif self.trade and self.target_ticket and e.order_id == self.target_ticket.order_id:
            self.stop_ticket.cancel()
            self.record("target")

    def exit_trade(self, reason):
        for tk in (self.stop_ticket, self.target_ticket):
            if tk and tk.status not in (OrderStatus.FILLED, OrderStatus.CANCELED):
                tk.cancel()
        sym, d = self.trade["symbol"], self.trade["dir"]
        if self.portfolio[sym].quantity != 0:
            self.market_order(sym, -self.portfolio[sym].quantity, tag=reason)
        self.record(reason)

    def record(self, reason):
        pnl = self.portfolio.total_portfolio_value - self.trade["equity"]
        self.results.append((reason, pnl))
        self.trade = None
        self.stop_ticket = self.target_ticket = None
        self.last_exit = self.time

    def round_tick(self, price):
        return round(round(price / self.tick) * self.tick, 6)

    def on_end_of_algorithm(self):
        n = len(self.results)
        if n == 0:
            self.log("No trades.")
            return
        wins = [p for _, p in self.results if p > 0]
        losses = [p for _, p in self.results if p <= 0]
        reasons = {}
        for r, _ in self.results:
            reasons[r] = reasons.get(r, 0) + 1
        pf = sum(wins) / -sum(losses) if losses and sum(losses) < 0 else float("inf")
        self.log(f"Trades {n} | win rate {100 * len(wins) / n:.1f}% | net ${sum(p for _, p in self.results):.2f} "
                 f"| profit factor {pf:.2f} | exits {reasons}")
