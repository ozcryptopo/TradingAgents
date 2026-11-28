# Gold / Dow divergence bot (TradingView)

A TradingView strategy based on the "20-Minute Trader" method: trade gold futures when gold
moves apart from the Dow, entering on a sharp RSI move against the trade.

**Paper-trade only until a few hundred trades show it makes money after costs.**

## Setup

1. TradingView Premium (needed for 1-second charts).
2. Open a chart of micro gold futures, `COMEX:MGC1!`, and set the timeframe to **1 second**.
3. Pine Editor → paste `gold_dow_divergence.pine` → **Add to chart**.
4. Optional, to see what the bot sees: add the indicators *Compare symbol* (`CBOT_MINI:YM1!`,
   percent scale) and *RSI* (length 5).

## Backtest

Open **Strategy Tester** at the bottom of the chart. Check:

- **Total closed trades:** below ~100 says little.
- **Percent profitable:** needs to beat about 50% at reward:risk 1, or 33% at 2.
- **Profit factor:** above 1.2 is a starting point.

TradingView keeps only a limited history of 1-second bars, so the backtest covers a short period.
Paper trading adds more data.

## Settings that replace the video's "feel"

| Setting | Default | Meaning |
|---|---|---|
| Divergence window | 120 s | The video's 90 s – 2 min trend |
| Min gold move | 0.03 % | How much gold must move in that window |
| Dow flat within | 0.01 % | How much the Dow can rise and still count as flat (mirror for sells) |
| Min gap | 0.04 % | How far apart the two moves must be |
| RSI length / timeframe | 5 / chart | "5-second" RSI; set timeframe to `5S` to match the video literally, but live results will then differ from the backtest |
| Min pop size | 15 RSI points | What counts as a "pop" |
| Pop vs normal wiggle | 3× | Pop must stand out from recent RSI movement |
| Stop placement | Pop extreme | Stop just beyond the low/high of the pop (my choice; the video gives no size) |
| Reward : risk | 1 | Video uses equal stop and target; try 2 too |
| Trading hours | 09:00–11:00 NY | Presenter trades from 9:00 ET |
| Max trades / day, daily loss limit | 5, $300 | Safety limits |

## Paper trading and automation

- **Paper trading:** at the bottom of the chart, connect *Paper Trading* and set an alert on the
  strategy, or log trades from the signals by hand.
- **Real orders:** TradingView alone does not send strategy orders to a broker. It needs a
  webhook alert (`{{strategy.order.alert_message}}` as the message) going to a service or broker
  that accepts webhooks. Each order already carries a small JSON message for this. Adjust it
  to whatever that service expects.
