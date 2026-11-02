# BLMI report store: setup

A website where anyone can pay for a facts-only market conditions report on any stock, ETF or crypto. It's
delivered automatically once it passes quality control.

```
Buyer → storefront → Stripe Checkout → webhook → order queue
      → worker: TradingAgents run → editing agent (facts only) → QC agent → branded PDF → email + download page
      → QC fails after fix rounds → held for your review (released after review, or refunded automatically at 24h)
      → run crashes twice → automatic full refund
```

| File | What it is |
|---|---|
| `REPORT_SPEC.md` | The rules every report agent follows (facts only, structure, formatting, QC criteria). Edit this to change the rules. |
| `SOCIAL_SPEC.md` | The rules for turning finished reports into Facebook/Instagram content. |
| `COMPLIANCE.md` | How the business runs: impersonal reports, covered symbols, conflicts, data licences, marketing claims, records. |
| `editor.py` | Editing agent: rewrites the run as facts only. Trader, risk and portfolio-manager text is never used. |
| `qc.py` | Quality-control agent: advice scan, number check, moving-average check, AI reviewer, final PDF scan. |
| `pipeline.py`, `worker.py` | The order pipeline and the worker loop. |
| `web.py`, `pages/` | Storefront, checkout, Stripe webhook, order status, downloads, admin. |

## 1. Accounts you need

1. **Stripe**: Developers → API keys → copy the **secret key** (start with test mode, `sk_test_…`).
2. **Supabase** (database + PDF storage):
   - Project Settings → Database → Connection string → **URI** (use the *Session pooler* one). This is `DATABASE_URL`.
   - Project Settings → API → copy the **service_role** key and the project URL.
   - Storage → New bucket → name `reports`, **Private**.
   - The app creates its `orders` table on first start (or run `schema.sql` in the SQL editor).
3. **Resend** (email): add and verify the domain `brightlaunchdigital.com`, then create an API key.
4. **Railway**: the host.

## 2. Deploy on Railway

1. New Project → Deploy from GitHub repo → `ozcryptopo/TradingAgents`, branch **`report-store`**. Railway reads
   `railway.json` and builds `Dockerfile.store`.
2. Simplest setup: **one service** with variable `ROLE=all` (website and worker together).
   Two-service setup (the worker can't slow down the website): create the service twice from the same repo, one with
   `ROLE=web` and one with `ROLE=worker`.
3. On the web service: Settings → Networking → Generate Domain (or add `reports.brightlaunchdigital.com`).
4. Add the variables below (Railway "Shared Variables" saves entering them twice).

| Variable | Value |
|---|---|
| `BASE_URL` | `https://<your Railway or custom domain>` |
| `DATABASE_URL` | Supabase session-pooler URI |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | from Supabase |
| `STRIPE_SECRET_KEY` | `sk_test_…` (then `sk_live_…`) |
| `STRIPE_WEBHOOK_SECRET` | from step 3 below |
| `RESEND_API_KEY` | from Resend |
| `EMAIL_FROM` | `BrightLaunch Market Intelligence <reports@brightlaunchdigital.com>` |
| `ADMIN_EMAIL` | where held reports and failures are sent |
| `ADMIN_KEY` | a long random password for `/admin` |
| `DEEPSEEK_API_KEY` | your DeepSeek key |
| `TRADINGAGENTS_LLM_PROVIDER` | `deepseek` |
| `TRADINGAGENTS_DEEP_THINK_LLM` / `TRADINGAGENTS_QUICK_THINK_LLM` | `deepseek-flash` (same as your Mac) |
| `FRED_API_KEY`, `CRYPTOETF_API_KEY` | same as your Mac's `.env` (optional `COINGLASS_API_KEY`), once their commercial terms are cleared (`COMPLIANCE.md` §6) |
| `SEC_EDGAR_USER_AGENT` | **Required**: your business name and a real email, e.g. `Bright Launch Digital Marketing reports@brightlaunchdigital.com` (SEC fair-access rule) |
| `OWNER_HOLDINGS` | Symbols you or the business hold, comma-separated; keep current (`COMPLIANCE.md` §4) |
| `BLOCKED_SYMBOLS` | Symbols never to sell reports or post about |
| Optional | `PRICE_QUICK_CENTS=900`, `PRICE_DEEP_CENTS=2900`, `DEEP_DEBATE_ROUNDS=3`, `QC_FIX_ROUNDS=2` |

## 3. Stripe webhook

Stripe → Developers → Webhooks → Add endpoint:
- URL: `https://<your domain>/api/stripe/webhook`
- Events: `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.expired`
- Copy the **signing secret** (`whsec_…`) into `STRIPE_WEBHOOK_SECRET` and redeploy.

## 4. Test it (test mode)

1. Open your domain, enter `BTC-USD`, pick Quick, your email, tick the box, pay with card `4242 4242 4242 4242`.
2. Watch the order page move through the stages. The PDF should arrive by email in about 10-20 minutes.
3. Open `https://<domain>/admin?key=<ADMIN_KEY>` to see the order, its quality-check report and the PDF.
4. Try a stock too (e.g. `NVDA`). Then switch the Stripe keys and webhook to live mode.

## 5. Before taking real payments (all required)

1. A securities lawyer has reviewed `REPORT_SPEC.md`, `SOCIAL_SPEC.md`, `COMPLIANCE.md`, `pages/terms.html` and the
   storefront copy.
2. Every "decision needed" data source in `COMPLIANCE.md` §6 is licensed for commercial use, replaced or turned off.
3. The website shows a contact email, a mailing address (P.O. box or virtual mailbox), the terms, a privacy policy and
   the refund policy, and states customers must be 18 or older.
4. Stripe has been told accurately what the business sells (an educational market-research publication) and has
   accepted it.
5. Symbol limits from `COMPLIANCE.md` §5 are switched on.
6. Ten or more test reports across stocks, ETFs and crypto have passed QC and been read in full by you, with no
   advice, forecasts or opinions found.

## 6. Running it

- **Admin page** `/admin?key=…`: every order, revenue, quality-check details. Held reports have **Send to customer**,
  **Re-run** and **Refund** buttons. Only press **Send to customer** after reading the whole PDF and confirming none
  of `REPORT_SPEC.md` §2's forbidden content is in it; add a note saying what you checked. Held reports not released
  within 24 hours of payment are refunded automatically.
- **Customer emails:** never answer "should I buy/sell" or questions about a customer's own money. Use the standard
  reply in `SOCIAL_SPEC.md` §11.
- **Costs per report**: DeepSeek usage (roughly $0.50-$2 for a deep run) plus Railway time. Stripe takes about
  2.9% + 30¢.
- **Changing rules**: edit `REPORT_SPEC.md` (reports), `SOCIAL_SPEC.md` (social posts) or `COMPLIANCE.md` (business
  policy) and redeploy. Wording rules take effect without code changes; the deterministic advice scan in `qc.py`
  should be updated to match any new forbidden wording.
- **Records:** keep orders, QC reports, delivered PDFs and posted content for at least 5 years (`COMPLIANCE.md` §9).
- **Every delivered report also saves a facts-only Markdown copy** next to the PDF (`BLMI_<TICKER>_<DATE>.md`). That
  is the input for social content (see `SOCIAL_SPEC.md`).

## Local run

```
pip install -e ".[store]"
DATABASE_URL=sqlite:///blmi_store.db ADMIN_KEY=dev uvicorn blmi_store.web:app --reload   # website
python -m blmi_store.worker                                                              # worker (needs DeepSeek key)
stripe listen --forward-to localhost:8000/api/stripe/webhook                             # Stripe CLI for webhooks
pytest tests/store
```

Do not charge real customers until every item in section 5 is done.
