# BLMI compliance policy: how the business stays a publisher, not an adviser

`REPORT_SPEC.md` and `SOCIAL_SPEC.md` control what the AI agents write. This document controls how the business runs:
what we sell, which symbols we cover, where our data comes from, how we market, and what we keep on file. It is a
plain-language working policy, not legal advice. **Have a securities lawyer review it, the specs, the terms page and
the storefront copy before charging real customers.**

## 1. Why the rules exist

- **Investment Advisers Act (SEC) and state law.** Anyone paid to advise others about securities is an investment
  adviser unless an exclusion applies. Ours is the **publisher's exclusion** (Supreme Court, *Lowe v. SEC*, 1985). It
  protects a *bona fide publication* that is (1) **impersonal**, not tailored to any reader; (2) **disinterested**,
  not used to promote securities we or a paying sponsor want to move; and (3) of **general and regular circulation**,
  not timed to specific market activity. South Dakota and other states follow similar rules.
- **Commodity Exchange Act (CFTC).** Advice about futures, swaps and leveraged crypto can make someone a commodity
  trading advisor. The same kind of publisher exclusion applies to general, impersonal publications.
- **Securities fraud rules (SEC Rule 10b-5, Securities Act §17(b)).** Promoting a symbol while trading against the
  promotion ("scalping"), or covering a symbol for undisclosed pay ("touting"), is unlawful for anyone, adviser or not.
- **FTC Act §5.** Every claim in ads, posts, the website and emails must be true and backed by evidence before it is
  made; disclosures must be clear and conspicuous; fake or AI-written reviews and testimonials are banned (FTC Rule on
  Consumer Reviews and Testimonials, 16 CFR Part 465) and endorsements follow the Endorsement Guides (16 CFR Part 255).
  Claims about AI must be accurate.
- **A disclaimer does not cure advice.** Regulators look at what content does, not what it is labeled.

## 2. What we sell (keeps us impersonal)

1. A report covers one symbol and is the **same for every buyer**. We never ask about, accept or use a buyer's
   holdings, goals, age, budget or questions, and there is no free-text field at checkout.
2. A later order for the same symbol, date and tier receives **the already-delivered report**, not a new run.
3. Reports are never "updated for you", re-run on request with a different angle, or followed up with personal notes.
4. Support emails, comments and DMs that ask for personal guidance get the standard reply in `SOCIAL_SPEC.md` §11.
5. No subscriptions, alerts, signal channels, chat rooms, coaching or one-on-one calls under the BLMI name. Any of
   those changes the legal analysis and needs a lawyer first.

## 3. Regular, general publication

- Keep a **regular publishing schedule** (for example, a weekly market conditions post and report on major symbols),
  available to the public, separate from paid orders.
- Never label content as an alert, flash report or breaking call, and never publish in reaction to a single price
  move "so people can act".
- Keep a public sample report on the website so anyone can see what a report contains before paying.

## 4. Conflicts of interest and personal trading

1. **Disclosure:** keep `OWNER_HOLDINGS` current with every symbol the owner or the business holds. Posts about those
   symbols carry the disclosure line (`SOCIAL_SPEC.md` §3.8); the terms page and every report carry the general
   conflicts disclosure.
2. **Blackout:** the owner and the business do not trade a symbol from **24 hours before to 48 hours after** a BLMI
   post or public report on it, and never trade against what was just published.
3. **No paid coverage:** never accept money, tokens, free allocations or other value from a company, fund, token
   project, exchange or promoter to cover, mention or post about a symbol.
4. **No affiliate links** to brokers or exchanges in reports or posts without a lawyer's review and a clear
   disclosure.

## 5. Which symbols we cover

Small, thinly traded symbols are where pump-and-dump schemes happen, and coverage of them carries the most risk.

- **Stocks and ETFs:** listed on a U.S. national exchange (NYSE, Nasdaq, NYSE American, Cboe) or a major foreign
  exchange; price at least **$5**; market value at least **$300 million**. No OTC or pink-sheet stocks, no SPACs
  before their merger closes.
- **Crypto:** in the **top 100 by market cap** with an established USD market; no newly launched tokens, meme coins
  outside the top 100, or tokens the owner helped launch or promote.
- `BLOCKED_SYMBOLS` lists anything else to refuse (for example, a symbol under an SEC trading suspension).
- The storefront refuses ineligible symbols before payment with a neutral message.

## 6. Data sources and licences

Selling reports is commercial use. Each source's terms must allow it. Status as of November 2, 2026:

| Source | Used for | Commercial use | Status |
|---|---|---|---|
| SEC EDGAR, CFTC, U.S. Treasury | Filings, fund flows, futures positioning | Public data; follow SEC fair-access rules (real name and email in `SEC_EDGAR_USER_AGENT`) | OK |
| FRED | Macro data | Federal series are public; some series are copyrighted by third parties (e.g. VIX by Cboe) | OK for federal series; check each third-party series' notes or drop it |
| Yahoo Finance (via `yfinance`) | Prices, indicators, news, symbol check | Yahoo's terms allow personal use only | **Decision needed** before launch |
| Coin Metrics Community | On-chain data | Licensed CC BY-NC 4.0: **non-commercial only** | **Decision needed** before launch |
| CryptoETF.today (free key) | Crypto ETF flows | Key was registered as a "personal research tool"; check terms and re-register the real use | **Decision needed** before launch |
| CoinGecko (free/demo) | Total crypto market cap | Demo plan terms limit commercial use; attribution required | **Check** |
| Reddit API, StockTwits | Sentiment | Commercial use needs their agreement | **Decision needed** (or drop sentiment from paid reports) |
| Hyperliquid, Polymarket | Funding/open interest, event odds | Public APIs; terms to confirm for commercial redistribution | **Check** |
| DeepSeek | AI models | Output is ours to use; never send customer personal data in prompts | OK |

Every "decision needed" row has the same options: buy a commercial licence, switch to a source that allows
commercial use, or drop that data from paid reports. Nothing is dropped without the owner's decision.

## 7. Marketing and website claims (FTC)

1. **Only claim what is true and documented.** Describe the quality check exactly as it works: figures are checked to
   come from the underlying data, key moving averages are recomputed from price data, and an AI reviewer screens for
   advice and errors. Never say every figure is "verified" or the report is "accurate".
2. **Delivery times** are stated as typical ("usually within an hour"), with the 24-hour review-or-refund promise.
3. **No earnings or performance claims:** never suggest reports help people make money, beat the market or "know
   before others"; no track records, hindsight posts or profit screenshots.
4. **No fake social proof:** no invented reviews, follower counts, customer numbers or "as seen in" badges.
5. **AI claims:** say plainly that reports and posts are AI-generated with automated checks; never imply a human
   analyst or credentials.
6. **Disclosures:** "Educational only. Not financial advice." sits on every page footer, the order form, every report
   page header, every email and every post, in readable size and contrast, not hidden behind links.
7. **Paid social ads:** Meta requires prior authorization for ads about crypto and certain financial services, and
   boosted posts count as ads. Get authorization before boosting any post about crypto or markets.
8. **Email:** order and delivery emails are transactional. Any marketing email needs opt-in, an unsubscribe link and
   a physical mailing address (CAN-SPAM); use a P.O. box or virtual mailbox, not a home address.

## 8. Orders, refunds and review

- The terms, the storefront and the emails must make the same promises, and the system must keep them: a held report
  is released after review or **refunded automatically 24 hours after payment**, and a failed run is refunded in full.
- A person releasing a held report must read the whole PDF, confirm none of `REPORT_SPEC.md` §2's forbidden content
  remains, and the release is recorded (who, when, note). A held report is never edited by hand outside the pipeline.
- The website shows the business name, a contact email, a mailing address, the terms, a privacy policy and the
  refund policy (Stripe also requires these). Customers must be 18 or older.

## 9. Records (keep at least 5 years)

- Every order: symbol, tier, price, time, consent text, IP address, QC report, fix rounds, reviewer actions, refunds.
- Every delivered report: the PDF and the facts-only Markdown.
- Every social post: the approved JSON, final images and video, post date and URL, and the `OWNER_HOLDINGS` value at
  the time.
- Every version of the specs, this policy, the terms and the storefront copy (Git history does this).
- Personal trades in covered symbols, with dates, to show the blackout was kept.
