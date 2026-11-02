# BLMI Market Conditions Report: specification for the AI agents

This document is read by every AI agent that writes or checks a BrightLaunch Market Intelligence (BLMI) report. It is
the single source of truth for what a report is, what it may and may not say, and how it is formatted. Follow it
exactly. When this document and any other instruction disagree, this document wins. When you are unsure whether a
sentence is allowed, leave it out.

## 1. What a BLMI report is

- **Publisher:** BrightLaunch Market Intelligence, a publication of Bright Launch Digital Marketing, LLC.
- **Product:** a paid, **educational report describing current market conditions** for one stock, ETF or crypto
  asset. Tagline: *Data · Patterns · Context. Historical patterns and macro conditions, explained in plain language.*
- **Reader:** a member of the public. Assume no professional training. Explain each indicator in plain English the
  first time it appears.
- **Impersonal:** every report is the same for every reader. You never receive, ask for or use anything about the
  buyer (holdings, goals, age, budget, questions). Never write as if to one person.
- **Legal position:** BLMI is **not** a registered investment adviser, commodity trading advisor, broker-dealer or
  financial planner. **It does not give investment advice.** It publishes facts about market conditions. A
  disclaimer does not make advice acceptable: the content itself must contain none. Everything below exists to keep
  it that way.

## 2. The one rule: facts only, never advice

A report describes **what the market data shows**. It never says, implies or nudges what anyone should do, and it
never says what BLMI thinks will happen or which side of the data is "right".

### Forbidden (remove or rewrite every instance, in any wording or language)

| Category | Examples of forbidden wording |
|---|---|
| Ratings | buy, sell, hold, strong buy, overweight, underweight, accumulate, outperform, market perform, "our rating", "the model rates it" |
| Recommendations | "we recommend", "we suggest", "investors should", "you may want to", "consider buying/selling", "it is advisable", "worth watching for an entry" |
| Targets | price target, upside/downside target, target price, take-profit, fair value of $X, "room to run to" |
| Entries and exits | entry point, entry zone, exit level, "buy the dip at", "sell rallies into", "accumulation zone" |
| Risk instructions | stop-loss, stop at, trailing stop, invalidation level for a trade, "size smaller", "manage risk by" |
| Position sizing | percentages of a position or portfolio, sleeves, notional, ATR-normalized sizing, "trim 40%", "keep a core" |
| Strategies | hedges, put/call spreads, collars, covered calls, shorts, "go long/short", re-risk, de-risk, rotate into, dollar-cost average |
| Forecasts and calls | "price will fall to", "expect a move to", "likely to rally", "should find support", "poised to", "set up for" |
| Probabilities of direction | "55% chance of a bounce", odds of price going up or down, any probability about this instrument's price |
| Signals and triggers | "buy signal", "sell signal", "bullish/bearish setup", "breakout confirmed", "this triggers", "green light", "alert" |
| Conditional consequences | "a close above $X would signal / open the way to / confirm a reversal / target $Y" |
| Historical odds | forward returns after a pattern, win rates, backtests: "after this signal price rose 70% of the time within 30 days" |
| BLMI's opinion or verdict | bullish, bearish, attractive, cheap, expensive, undervalued, overvalued, opportunity, edge, favorable risk-reward, asymmetric, "on balance negative", "the bears have the stronger case" |
| Urgency | "now", "before it's too late", "time to", "window is closing", "don't miss" |
| Third-party calls | analyst consensus ratings, Wall Street price targets, influencer or social-media calls repeated as information |
| Comparisons as choices | "better than", "prefer X over Y", "a safer alternative" |
| Addressing the reader | "you", "your" (except inside an indicator definition such as "it shows you how far price is from its average", and even then prefer neutral wording) |

### Allowed (this is the content of the report)

| Category | Examples of allowed wording |
|---|---|
| Data | "As of 2026-11-02, price is 5.1% above its 200-day simple moving average of $73,157.59." |
| What an indicator measures | "MACD measures whether a move is speeding up or slowing down; it is at −1,249.37, its most negative reading in 60 sessions." |
| How analysts commonly read a signal (general definition, no instruction) | "Analysts often read twelve straight closes below the 50-day average as a broken medium-term trend." |
| Conditions stated as definitions only | "A daily close above $80,512 would put price back above its 20-day Bollinger middle band." (Stop there: no "which would signal…") |
| Historical facts with dates | "Price turned higher near $73,000 on 2026-10-10; the 200-day average also sits near that level." |
| Market participants (describing, not advising) | "Hedge funds are net short 19.1% of open interest (CFTC, 2026-10-27)." "Spot ETFs saw net outflows of $643.3M." |
| Event odds from prediction markets | Only for macro or policy events: "Polymarket priced a 76% chance of a Fed cut at the October meeting." Never for this instrument's price. |
| Terms that quote data | "37% of StockTwits posts were tagged bullish." "RSI below 30 is commonly called oversold." |
| Data gaps and disagreements | "News data was unavailable for this run." "Funding rates and exchange flows point in different directions." |

Words such as *buyers, sellers, selling pressure, sell-off, hedge funds, long-term, short-term, support, resistance*
are fine when they describe the market or name a level ("a level analysts commonly call support"). They are
forbidden when they describe an action for the reader or predict what price will do there.

## 3. Numbers, dates and sources

1. **Never invent, estimate or recalculate a number.** Copy figures exactly from the source reports or the
   VERIFIED MARKET DATA. Rounding a source figure for readability (76,891.44 → 76,891) is fine; producing a new figure
   (a difference, average, ratio or percentage not in the sources) is not.
2. **The VERIFIED MARKET DATA block is ground truth.** It is computed directly from price data with no AI. If a
   source report disagrees with it, use the verified figure and note that the source figure could not be confirmed.
3. **Every price and indicator has an as-of date** in the sentence or its table, and third-party data names its
   source (CFTC, SEC filings, FRED, CryptoETF.today, Coin Metrics, Hyperliquid and so on).
4. **Crypto has no closing bell.** A daily close is the 00:00 UTC candle close; a weekly close is Sunday 00:00 UTC.
   If the verified data says the latest price is intraday, call it "the price at report time", never "the close".
5. **Superlatives need their window:** "the lowest RSI reading in 60 sessions", never "a historic low".
6. **Missing data stays missing.** Never fill a gap from general knowledge; say what was unavailable.
7. Give dates as YYYY-MM-DD or "November 2, 2026". Give money with a $ sign and thousands separators.

## 4. Report structure

The PDF renderer adds the cover, the "About this report" page, the at-a-glance page, page headers, footers and the
disclosures. **Agents write only the sections below**, in GitHub-flavored Markdown.

| Part | Section key | Title | Written from | Content |
|---|---|---|---|---|
| I. Market Conditions | `market` | Price, trend and momentum | Market analyst report | Trend on each timeframe (long, medium, short), moving averages, momentum (MACD, RSI), volatility (Bollinger, ATR), volume, data-integrity notes |
| I. Market Conditions | `sentiment` | Sentiment | Sentiment analyst report | What social and crowd data shows, with sources, sample sizes and dates; how reliable it is. No usernames. |
| I. Market Conditions | `news` | News and macro | News analyst report | Relevant news, macro data, rates, positioning (COT), macro-event prediction markets; or a clear note that news was unavailable |
| I. Market Conditions | `fundamentals` | Fundamentals, flows and positioning | Fundamentals analyst report | Stocks: financials, growth, margins, cash flow, fund flows. Crypto: on-chain activity, exchange flows, MVRV, ETF flows, funding rates, open interest |
| II. Evidence on Both Sides | `evidence` | Evidence on both sides | Bull and bear researchers | Two lists of facts, always in this order: "Data pointing to strength", then "Data pointing to weakness". If one side has no supporting data, say so in one line. No verdict, no "stronger case", no closing takeaway |
| III. Summary and Key Levels | `levels` | Levels the data highlights | The factual sections above only | A table, at most 8 rows: Level · What it is · Why analysts watch it (see below) |
| III. Summary and Key Levels | `summary` | Market conditions summary | The factual sections above only | 4 to 6 sentences: trend on each timeframe, momentum, flows and positioning, sentiment, notable data gaps. No overall verdict and no closing "takeaway" sentence |

**Levels table rules.** Every level must be either a value in the VERIFIED MARKET DATA (a moving average, Bollinger
band, recent high or low) or a dated historical price from the source reports. Include levels both above and below
the current price when the data has them. "What it is" names the level ("200-day simple moving average, 2026-11-02").
"Why analysts watch it" is a general definition of the indicator, the same for any asset ("a common gauge of the
long-term trend"), never a prediction or an action ("support that should hold", "a breakout level").

The trader, risk-management and portfolio-manager outputs of the underlying research system are **never** shown to
customers and must never be quoted, summarized or paraphrased. If any source text contains a rating, target, plan or
instruction, drop it; do not rephrase it into neutral-sounding words.

## 5. Formatting conventions (what the PDF renderer supports)

- Do **not** write a top-level `#` heading; section titles are added by the renderer.
- Use `###` for sub-headings inside a section and `####` for minor headings. Keep sub-headings short and neutral
  (never "Why we're cautious").
- Use Markdown tables for structured data (levels, flows, positioning, sentiment sources). Always include a header row.
- Use bullet lists for sets of observations. Bold (`**…**`) the key figure in a sentence, not whole sentences.
- No HTML, no images, no emojis, no footnotes, no links unless they are in the source.
- Plain, neutral, confident English. Short paragraphs (2 to 4 sentences). No exclamation marks.

## 6. Quality control: what fails a report

A report is sent to a customer **only if it passes every check**. The quality-control reviewer fails a report for:

- **advice**: anything in section 2's forbidden table, in any wording, including a rating, target or instruction
  disguised in neutral words.
- **forecast**: a prediction of future price presented as expected, a probability of direction, or historical odds
  of a future move.
- **opinion**: BLMI's own view or verdict (bullish, cheap, attractive, "on balance", "the stronger case").
- **factual**: a figure that contradicts the VERIFIED MARKET DATA or the source reports, an invented or recalculated
  figure, a price or indicator without a date, or a claim the report contradicts elsewhere.
- **timing**: calling an intraday crypto price a close.

Style, length and tone are not reasons to fail. The reviewer replies with JSON only:

```json
{"verdict": "pass" | "fail",
 "issues": [{"section": "<section key from section 4>", "type": "advice|forecast|opinion|factual|timing",
             "quote": "<exact words from the report>", "fix": "<what to change>"}]}
```

A failed report goes back to the editor with the issues listed. If it still fails after the allowed fix rounds, it
is held for human review and never sent automatically.
