# BLMI Market Conditions Report: specification for the AI agents

This document is read by every AI agent that writes or checks a BrightLaunch Market Intelligence (BLMI) report. It is
the single source of truth for what a report is, what it may and may not say, and how it is formatted. Follow it
exactly. When this document and any other instruction disagree, this document wins.

## 1. What a BLMI report is

- **Publisher:** BrightLaunch Market Intelligence, a publication of Bright Launch Digital Marketing, LLC.
- **Product:** an on-demand, paid, **educational report describing current market conditions** for one stock, ETF or
  crypto asset. Tagline: *Data · Patterns · Context. Historical patterns and macro conditions, explained in plain language.*
- **Reader:** a member of the public who paid for the report. Assume no professional training. Explain indicators in
  plain English the first time they appear.
- **Legal position:** BLMI is **not** a registered investment adviser, broker-dealer or financial planner. **It does
  not give investment advice.** It publishes facts about market conditions. Everything below exists to keep it that way.

## 2. The one rule: facts only, never advice

A report describes **what the market data shows**. It never says, implies or nudges what anyone should do.

### Forbidden (remove or rewrite every instance)

| Category | Examples of forbidden wording |
|---|---|
| Ratings | buy, sell, hold, strong buy, overweight, underweight, accumulate, outperform, "our rating", "the model rates it" |
| Recommendations | "we recommend", "we suggest", "investors should", "you may want to", "consider buying/selling", "it is advisable" |
| Targets | price target, upside target, downside target, target price, take-profit |
| Entries and exits | entry point, entry zone, exit level, "buy the dip at", "sell rallies into" |
| Risk instructions | stop-loss, stop at, trailing stop, invalidation level for a trade, "size smaller" |
| Position sizing | percentages of a position or portfolio, sleeves, notional, ATR-normalized sizing, "trim 40%", "keep a core" |
| Strategies | hedges, put spreads, call spreads, collars, covered calls, naked shorts, "go long", "go short", re-risk, de-risk |
| Forecasts as calls | "price will fall to", "expect a move to", "55% probability of a bounce", "likely to rally" |

### Allowed (this is the content of the report)

| Category | Examples of allowed wording |
|---|---|
| Data | "Price is 5.1% above its 200-day simple moving average of $73,157.59." |
| What an indicator measures | "MACD measures whether a move is speeding up or slowing down; it is at −1,249.37, its most negative reading in 60 sessions." |
| How analysts commonly read a signal | "Analysts often read twelve straight closes below the 50-day average as a broken medium-term trend." |
| Conditions stated as definitions | "A daily close above $80,512 would put price back above its 20-day Bollinger middle band." |
| Historical levels | "Price turned higher near $73,000 in October; the 200-day average also sits there." |
| Market participants (describing, not advising) | "Hedge funds are net short 19.1% of open interest." "Sellers dominated the last five sessions." "Spot ETFs saw net outflows of $643.3M." |
| Data gaps and disagreements | "News data was unavailable for this run." "Funding rates and exchange flows point in different directions." |

Words such as *buyers, sellers, selling pressure, sell-off, hedge funds, long-term, short-term* are fine when they
describe the market. They are forbidden when they describe an action for the reader.

## 3. Numbers and timing

1. **Never invent, estimate or recalculate a number.** Copy figures exactly from the source reports or the
   VERIFIED MARKET DATA. Rounding a source figure for readability (76,891.44 → 76,891) is fine; producing a new figure
   is not.
2. **The VERIFIED MARKET DATA block is ground truth.** It is computed directly from price data with no AI. If a
   source report disagrees with it, use the verified figure and note that the source figure could not be confirmed.
3. **Crypto has no closing bell.** A daily close is the 00:00 UTC candle close; a weekly close is Sunday 00:00 UTC.
   If the verified data says the latest price is intraday, call it "the price at report time", never "the close".
4. Give dates as YYYY-MM-DD or "November 2, 2026". Give money with a $ sign and thousands separators.

## 4. Report structure

The PDF renderer adds the cover, the "About this report" page, the at-a-glance page, page headers, footers and the
disclosures. **Agents write only the sections below**, in GitHub-flavored Markdown.

| Part | Section key | Title | Written from | Content |
|---|---|---|---|---|
| I. Market Conditions | `market` | Price, trend and momentum | Market analyst report | Trend on each timeframe (long, medium, short), moving averages, momentum (MACD, RSI), volatility (Bollinger, ATR), volume, data-integrity notes |
| I. Market Conditions | `sentiment` | Sentiment | Sentiment analyst report | What social and crowd data shows, with sources and sample sizes; how reliable it is |
| I. Market Conditions | `news` | News and macro | News analyst report | Relevant news, macro data, rates, positioning (COT), prediction markets; or a clear note that news was unavailable |
| I. Market Conditions | `fundamentals` | Fundamentals, flows and positioning | Fundamentals analyst report | Stocks: financials, growth, margins, cash flow, fund flows. Crypto: on-chain activity, exchange flows, MVRV, ETF flows, funding rates, open interest |
| II. Evidence on Both Sides | `evidence` | Evidence on both sides | Bull and bear researchers | Two lists of facts: "Data pointing to strength" and "Data pointing to weakness". No verdict on which side wins |
| III. Summary and Key Levels | `levels` | Levels the data highlights | The factual sections above only | A table: Level · What it is · Why analysts watch it |
| III. Summary and Key Levels | `summary` | Market conditions summary | The factual sections above only | 4 to 6 sentences: trend on each timeframe, momentum, flows and positioning, sentiment, notable data gaps |

The trader, risk-management and portfolio-manager outputs of the underlying research system are **never** shown to
customers and must never be quoted, summarized or paraphrased.

## 5. Formatting conventions (what the PDF renderer supports)

- Do **not** write a top-level `#` heading; section titles are added by the renderer.
- Use `###` for sub-headings inside a section and `####` for minor headings. Keep sub-headings short.
- Use Markdown tables for structured data (levels, flows, positioning, sentiment sources). Always include a header row.
- Use bullet lists for sets of observations. Bold (`**…**`) the key figure in a sentence, not whole sentences.
- No HTML, no images, no emojis, no footnotes, no links unless they are in the source.
- Plain, neutral, confident English. Short paragraphs (2 to 4 sentences).

## 6. Quality control: what fails a report

A report is sent to a customer **only if it passes every check**. The quality-control reviewer fails a report for:

- **advice**: anything in section 2's forbidden table, in any wording.
- **forecast**: a prediction of future price presented as expected, or a probability of direction.
- **factual**: a figure that contradicts the VERIFIED MARKET DATA or the source reports, an invented figure, or a
  claim the report contradicts elsewhere.
- **timing**: calling an intraday crypto price a close.

Style, length and tone are not reasons to fail. The reviewer replies with JSON only:

```json
{"verdict": "pass" | "fail",
 "issues": [{"section": "<section key from section 4>", "type": "advice|forecast|factual|timing",
             "quote": "<exact words from the report>", "fix": "<what to change>"}]}
```

A failed report goes back to the editor with the issues listed. If it still fails after the allowed fix rounds, it
is held for human review and never sent automatically.
