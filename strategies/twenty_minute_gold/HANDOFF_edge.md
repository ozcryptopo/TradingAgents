# Handoff 4: measure the raw edge (no fees, no slippage)

You are Claude in Chrome, working in the QuantConnect project **GoldDowDivergence**, which holds the
291-line main_v4 code.

Purpose: every rule so far lost about $935 over Sep–Oct 2025. This checks whether any of them would
make money *before* costs. If none do, the idea is dead at this speed and we stop.

## Step 1: two small edits to main.py

**Edit 1.** Directly above the line `        # ---- data: continuous front-month contracts, 1-second bars ----`
insert these two lines (8-space indent, then a blank line):

```python
        self.costs = self.get_parameter("costs", 1)  # 0 = no fees or slippage (to measure raw edge)

```

**Edit 2.** In `on_securities_changed`, replace these three lines:

```python
        # ~1 tick of slippage on gold market and stop orders
        for s in changes.added_securities:
            s.set_slippage_model(ConstantSlippageModel(0.00003))
```

with:

```python
        # ~1 tick of slippage on gold market and stop orders; costs = 0 removes fees and slippage
        for s in changes.added_securities:
            if self.costs:
                s.set_slippage_model(ConstantSlippageModel(0.00003))
            else:
                s.set_slippage_model(NullSlippageModel())
                s.set_fee_model(ConstantFeeModel(0))
```

The file should now be 297 lines. Save; the Problems tab should show only the 2 usual `add_future` warnings.

## Step 2: three runs, all with `costs` = `0`, `max_trades` = `20`, `rr` = `1`

`max_trades` = 20 lifts the 5-per-day cap so we get more trades to judge by.

| Run | `rule` | `invert` |
|---|---|---|
| E1 | `rsi` | `0` (original video rule) |
| E2 | `rsi` | `1` (reversed) |
| E3 | `lead` | `0` (index leads, gold follows) |

For each run report: Net Profit, Total Fees (should be $0), Win Rate, Profit-Loss Ratio, Drawdown, and
the last Logs line ("Trades ...").

Afterwards set `costs` back to `1` and `max_trades` back to `5` (or delete both parameters).

## Rules
- Backtests only (▶). Never ⚡ Go Live, brokerage, billing, subscriptions or Make Public.
- If anything asks for payment or an upgrade, stop and tell me.
- No code changes beyond the two edits above. If there's an error, report the full text and line number.
