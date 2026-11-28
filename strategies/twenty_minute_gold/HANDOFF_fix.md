# Handoff 2: fix and rerun the GoldDowDivergence backtest on QuantConnect

You are Claude in Chrome. The QuantConnect project **GoldDowDivergence** already exists in my account.
Its first backtest found a bug: the entry fill arrived before `market_order()` returned, so the trade
was never managed. Apply the three edits below to `main.py`, exactly as written, then rerun.

## Edit 1: recognise the entry fill by its tag
In `on_order_event`, find this line:

```python
        if self.entry_ticket and e.order_id == self.entry_ticket.order_id and self.pending:
```

Replace that one line with these three lines (8-space indent):

```python
        tag = self.transactions.get_order_by_id(e.order_id).tag
        if self.pending and self.trade is None and tag in ("buy", "sell"):
```

(That's 2 lines; the comment is optional.)

## Edit 2: rename `record` to `record_trade`
Find and replace (Ctrl+H) `self.record(` with `self.record_trade(`. There are 3 occurrences.
Then change `def record(self, reason):` to `def record_trade(self, reason):`.

## Edit 3: add a safety net
In `on_data`, directly above the line `        # manage an open trade`, insert (8-space indent):

```python
        if self.trade is None and self.pending is None and self.portfolio.invested:
            self.liquidate(tag="untracked position")

```

## Then
1. Save. Check the Problems tab shows no errors (warnings are fine).
2. Run Backtest (▶ only, never ⚡ Go Live). Wait for it to finish.
3. Report: Net Profit, Total Orders, Win Rate, Loss Rate, Profit-Loss Ratio, Drawdown, Sharpe Ratio,
   Total Fees, and the last line of the Logs tab (starts "Trades ...").
4. Second run: Parameters → add `rr` = `2` → backtest again → report the same numbers.
5. If the Logs line shows fewer than 30 trades in the first run, do a third run with `rr` = `1` and
   `session_end` = `16:00`, and report that too.

## Rules
- Don't change account settings, subscriptions or billing. Stop and tell me if asked to pay or upgrade.
- No live trading, no brokerage connection.
- If there's an error, report the full text and line number. Don't change anything other than the
  three edits above.
