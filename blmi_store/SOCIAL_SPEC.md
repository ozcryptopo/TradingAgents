# BLMI social content: specification for the AI agents

This document is read by every AI agent that turns a BrightLaunch Market Intelligence (BLMI) report into social media
content for the **BrightLaunch Market Intelligence Facebook Page** (and, unchanged, Instagram, Threads and X). It sits
beside `REPORT_SPEC.md`, which defines the reports themselves. **Every rule in REPORT_SPEC.md section 2 (facts only,
never advice) and section 3 (numbers and timing) applies here too, and is stricter on social media**, where a post
travels without its disclaimers and context.

## 1. Purpose and voice

- **Goal:** teach people how to read market conditions, using the real numbers from a BLMI report as the example, and
  build trust in BLMI so readers follow the Page and order reports.
- **Brand line:** *Data · Patterns · Context. Historical patterns and macro conditions, explained in plain language.*
- **Voice:** calm, plain-spoken, curious, a good teacher. Confident about facts, never hype. No slang about money
  ("moon", "pump", "to the moon", "rekt", "load up"), no fear or urgency ("before it's too late", "don't miss").
- **Audience:** everyday people interested in markets. Explain every indicator the first time, in one sentence.

## 2. The only allowed input

Agents work **only from the facts-only report Markdown** that the BLMI report pipeline saves next to each delivered PDF
(`BLMI_<TICKER>_<DATE>.md`). That file has already been edited to facts only and passed quality control. Never use
the raw TradingAgents output, trader/risk/portfolio-manager text, or your own market knowledge. If a fact is not in
the report Markdown, it does not go in a post.

## 3. Compliance rules for posts (all mandatory)

1. **No advice, ratings, targets, entries, exits, stops, sizing or strategies**, in any wording (REPORT_SPEC.md §2).
2. **No calls or predictions.** Never say or imply where price is going. Questions that invite a prediction from the
   audience ("Where do you think BTC goes next?") are not allowed either. Ask about understanding instead ("Which of
   these indicators do you check first?").
3. **No "bullish"/"bearish" as BLMI's view.** These words may appear only when quoting data that uses them
   ("37% of StockTwits posts were tagged bullish").
4. **Every figure comes from the report**, copied exactly or rounded for readability, with its date. Always say
   "as of <date>" for prices and indicators. For crypto intraday prices say "at report time", never "close".
5. **No performance claims** about BLMI or its reports ("our AI called it", "accurate", "proven"), no testimonials
   unless they are real and approved, and no guarantees of any kind.
6. **Disclaimer on every post.** The caption ends with: `Educational content only. Not financial advice.` Every
   image and video frame carries the footer `Education only · Not financial advice`.
7. **No impersonation or third-party branding.** No exchange, fund or company logos, no celebrities, no screenshots
   of other people's charts or posts. Quote social posts only as the report already does, without usernames.
8. **Promotion of BLMI reports is allowed** ("Want the full report on a symbol? Order one at <site>"), stated plainly
   with the price as listed on the site. Never imply the report will tell people what to buy or sell.

If a draft cannot follow these rules, drop that post rather than weaken a rule.

## 4. What to make from each report

From one report, produce this set (the posting schedule is in section 6):

| # | Format | Spec |
|---|---|---|
| A | **Carousel** (Facebook multi-photo / Instagram carousel) | 6 to 8 slides, 1080×1350. Slide 1 hook; slides 2-5 one lesson each, with the real figure and a one-sentence "what this measures" line; slide 6 the levels the data highlights (from the report's levels table); last slide the summary + call to action. |
| B | **Reel / short video script** | 25 to 40 seconds, 1080×1920, 5 to 7 scenes. Each scene: on-screen text (max 12 words), voiceover line, duration in seconds. First 2 seconds must hook. |
| C | **Single-image stat post** | One striking figure from the report with a one-line explanation, 1080×1350. |
| D | **Text post** | 80 to 150 words teaching one concept from the report (e.g. what the 200-day average is and where price sits against it). |
| E | **Poll or question post** (optional) | An understanding question with 2 to 4 options (see rule 3.2). |

### Lessons that work well (pick the 3 to 4 strongest in the report)

- Timeframes disagree: long, medium and short-term trends from the moving averages.
- Momentum: MACD and RSI, and whether momentum is improving or worsening.
- Follow the money: ETF/fund flows, futures positioning (COT), funding rates, exchange balances.
- Fundamentals in plain English (stocks): growth, margins, cash flow, leverage.
- Sentiment versus data: when the crowd and the numbers disagree.
- Data gaps: what was missing, and why honest reports say so.
- Crypto timing: there is no closing bell; a daily close is 00:00 UTC.

## 5. Copy formats

- **Hook (slide 1 / first line / first 2 seconds):** a factual tension or question about understanding, under 12
  words. Good: "Bitcoin's trends disagree. Here's how to read that." "3 numbers that explain this week's selloff."
  Not allowed: "Is this the bottom?" "Is the bull market over?" (invites a prediction), "Buy signal?".
- **Caption:** hook line → 2 to 4 short lines of value → "Swipe to learn…" or the lesson list → CTA → disclaimer →
  hashtags. Keep under 220 words. Use at most 3 emojis, only as bullets or markers.
- **CTA options:** "Follow BrightLaunch Market Intelligence for plain-language market data." / "Comment a symbol
  you'd like us to explain next." / "Full facts-only reports on any stock or crypto: <site>."
- **Hashtags:** 4 to 8, mixing the symbol and education tags, e.g. `#bitcoin #btc #marketeducation
  #technicalanalysis #learntotrade #investingeducation`. Never `#buy`, `#sell`, `#signals`, `#100x` or similar.
- **Numbers:** `$76,891` for display (from $76,891.44), `−6.1%` with a real minus sign, dates as "Nov 2, 2026".

## 6. Posting schedule per report

- **Day 0:** Reel (B). Video reaches the most people.
- **Day 1:** Carousel (A).
- **Day 2:** Single-image stat (C) or text post (D).
- **Day 3 (optional):** Poll (E).
- Never post figures more than 3 days after the report's date without saying they are from that date.

## 7. Visual style

- **Colors:** navy `#0b1e3f` background, gold `#ffd166` highlights, orange `#f4811e` accents, white text; green
  `#3ddc97` for "above / inflow", red `#ff5c5c` for "below / outflow" (colour describes the data, never a call).
- **Type:** Space Grotesk or Inter Display for headlines, Inter for body.
- **Every slide/frame:** small header `AI Research Desk · <TICKER>`, footer `BrightLaunch Market Intelligence` and
  `Education only · Not financial advice`. Keep text out of the outer 120 px (platform buttons cover it).
- **Charts:** draw only levels and values that are in the report. Never draw a projected price path.
- **AI images (optional, for covers and B-roll):** abstract only (light trails, data grids, gauges, a stylized
  trading room). No people's faces, logos, coins with real-brand marks, or text inside the AI image; add text on top.

## 8. Output format for the posting bot

Return one JSON object, no other text:

```json
{
  "report": {"ticker": "BTC-USD", "date": "2026-11-02", "source_file": "BLMI_BTC-USD_2026-11-02.md"},
  "posts": [
    {"id": "A", "format": "carousel", "day": 1,
     "slides": [{"headline": "", "body": "", "figure": "", "figure_label": ""}],
     "caption": "", "hashtags": []},
    {"id": "B", "format": "reel", "day": 0,
     "scenes": [{"seconds": 4, "on_screen": "", "voiceover": ""}],
     "caption": "", "hashtags": []},
    {"id": "C", "format": "stat_image", "day": 2, "figure": "", "figure_label": "", "explanation": "",
     "caption": "", "hashtags": []},
    {"id": "D", "format": "text", "day": 2, "text": "", "hashtags": []},
    {"id": "E", "format": "poll", "day": 3, "question": "", "options": [], "caption": ""}
  ],
  "image_prompts": [""],
  "facts_used": [{"figure": "", "where_in_report": ""}]
}
```

`facts_used` lists every figure that appears in any post and where it is in the report Markdown, so a checker can
verify it. Every caption must end with `Educational content only. Not financial advice.` before the hashtags.

## 9. Checking posts before they go out

Social posts pass the same quality control as reports (REPORT_SPEC.md §6), plus:

- every figure appears in the report Markdown (check `facts_used`);
- every caption has the disclaimer line, and every visual has the footer;
- no prediction-inviting questions and no "bullish/bearish" as BLMI's view;
- dates are stated for every price and indicator.

Any failure: fix and re-check. Never post a draft that has not passed.
