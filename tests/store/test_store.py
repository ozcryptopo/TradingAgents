"""BLMI report store: compliance checks, the order pipeline and the web flows, with fakes for AI, Stripe and email."""

import hashlib
import hmac
import json
import time
from pathlib import Path

import pandas as pd
import pytest

from blmi_store import db, editor, market_facts, pipeline, qc
from blmi_store.config import Settings
from blmi_store.delivery import Storage

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------- compliance checks

ADVICE = [
    "Rating: Underweight", "Reduce net exposure by 40-50%.", "Keep a core at 50-60% of a standard sleeve.",
    "Use a 65k-70k put spread.", "Set a stop-loss at 72,900.", "Investors should wait for confirmation.",
    "We recommend trimming here.", "Do not initiate new longs at this level.", "The price target is 90,000.",
    "This is a sell signal.", "Consider buying near support.", "Avoid naked shorts.", "Work the order into a ladder.",
]
FACTS = [
    "Price is 5.1% above its 200-day average.", "Spot ETFs saw net outflows of $643.3M.",
    "Hedge funds are net short 19.1% of open interest.", "Sellers dominated the last five sessions.",
    "The sell-off took price below the 50-day average.", "Long-term trend: price above the 200-day average.",
    "Moody's credit rating for the company is A2.", "Buyers absorbed supply near $73,000.",
]


@pytest.mark.parametrize("text", ADVICE)
def test_advice_is_caught(text):
    assert qc.advice_hits(text), text


@pytest.mark.parametrize("text", FACTS)
def test_market_facts_are_not_flagged(text):
    assert not qc.advice_hits(text), qc.advice_hits(text)


def test_unsupported_numbers():
    source = "Close 76,891.44; 200 SMA 73,157.59; MACD -1,249.37; ETF flow -$643.3M; 6.13% below"
    ok = "Price $76,891 sits above the 73,157.59 average; MACD -1,249.37; outflow $643.3M; 6.1% below; 14-day RSI; 2026"
    assert qc.unsupported_numbers(ok, source) == []
    assert qc.unsupported_numbers("A new level at 81,500 and 12.4%", source) == ["12.4", "81,500"]


def test_moving_average_mismatch():
    facts = {"sma_200": 73157.59, "sma_50": 81916.98}
    assert qc.moving_average_mismatches("the 200-day average of $73,157.59", facts) == []
    assert qc.moving_average_mismatches("the 200-day average at 75,500", facts)


def test_specs_load_into_agent_prompts():
    assert "facts only" in editor.editor_system().lower()
    assert "verdict" in qc.reviewer_system()
    assert (Path(editor.__file__).with_name("SOCIAL_SPEC.md")).exists()


# ---------------------------------------------------------------- pipeline with fakes

STATE = {
    "market_report": "BTC closed at 76,891.44, 5.10% above the 200 SMA at 73,157.59. Rating: Underweight.",
    "sentiment_report": "Sentiment is mixed.",
    "news_report": "News data unavailable for this run.",
    "fundamentals_report": "ETF flow -$643.3M. Exchange supply -69,603 BTC.",
    "investment_debate_state": {"bull_history": "Bull: above 200 SMA 73,157.59.", "bear_history": "Bear: ETF -$643.3M."},
    "trader_investment_plan": "Sell 40-50% and buy a put spread.",
    "final_trade_decision": "Rating: Underweight. Trim the position.",
}
FACTS_DICT = {"ticker": "BTC-USD", "asset_type": "crypto", "analysis_date": "2026-11-02", "last_close": 77198.21,
              "last_close_date": "2026-11-01", "sma_50": 81916.98, "sma_200": 73157.59, "live_price": 76891.44,
              "live_time_utc": "2026-11-02 18:55", "open_candle_date": "2026-11-02", "reference_price": 76891.44,
              "vs_sma_200_pct": 5.1, "trend_value": "Above 200-day average",
              "trend_note": "Price 5.1% above the 200-day average of $73,157.59"}


class FakeLLM:
    """Plays the editor and the reviewer. ``advice_rounds`` makes the editor leak advice that many times."""

    def __init__(self, advice_rounds=0, reviewer="pass"):
        self.advice_rounds, self.reviewer, self.calls = advice_rounds, reviewer, []

    def __call__(self, system, user):
        self.calls.append(user)
        if "YOUR ROLE: you are the BLMI quality-control reviewer" in system:
            return json.dumps({"verdict": self.reviewer, "issues": [] if self.reviewer == "pass" else
                               [{"section": "market", "type": "factual", "quote": "x", "fix": "y"}]})
        if "=== SUMMARY ===" in user:
            return ("=== SUMMARY ===\nPrice is 5.10% above the 200-day average of 73,157.59.\n=== LEVELS ===\n"
                    "| Level | What it is | Why analysts watch it |\n|---|---|---|\n| 73,157.59 | 200-day SMA | Long-term trend |")
        if self.advice_rounds > 0 and "Section: Price, trend" in user:
            self.advice_rounds -= 1
            return "Price is 76,891.44 at report time. Rating: Underweight."
        return "Price is **76,891.44** at report time, 5.10% above the 200-day average of 73,157.59."


@pytest.fixture
def env(tmp_path):
    cfg = Settings(base_url="https://store.test", database_url=f"sqlite:///{tmp_path}/t.db",
                   local_storage_dir=str(tmp_path / "files"), work_dir=str(tmp_path / "work"),
                   admin_email="oi@test", admin_key="k", stripe_webhook_secret="whsec_test")
    engine = db.make_engine(cfg.database_url)
    sent = []

    def make(llm, run=None, pdf_problems=()):
        def render(ticker, state, settings, parts, out_dir):
            assert "final_trade_decision" not in state           # nothing that carries a rating reaches the PDF
            assert settings["edition"] == "educational"
            text = json.dumps(parts)
            assert "put spread" not in text                      # decision agents' text never reaches the PDF
            path = Path(out_dir) / "r.pdf"
            path.write_bytes(b"%PDF-1.7 " + text.encode())
            return True, str(path)
        return pipeline.Deps(
            cfg=cfg, engine=engine, llm=llm,
            run_analysis=run or (lambda *a: (STATE, {"analysts": ["market"]})),
            compute_facts=lambda *a: FACTS_DICT, render_pdf=render, check_pdf=lambda p: list(pdf_problems),
            storage=Storage(cfg), send_email=lambda cfg, to, subj, html, att: sent.append((to, subj, att)) or True,
            refund=lambda cfg, pi: True)
    return cfg, engine, sent, make


def _paid(engine):
    o = db.create_order(engine, email="buyer@test", ticker="BTC-USD", asset_type="crypto", tier="deep",
                        amount_cents=2900, consent_text="c", consent_ip="1.1.1.1")
    db.set_fields(engine, o["id"], status="queued", analysis_date="2026-11-02", stripe_payment_intent="pi_1")
    return db.claim_next(engine)


def test_clean_report_is_delivered(env):
    cfg, engine, sent, make = env
    order = _paid(engine)
    assert pipeline.process(order, make(FakeLLM())) == "delivered"
    row = db.get(engine, order["id"])
    assert row["status"] == "delivered" and row["pdf_path"].endswith(".pdf")
    md = Storage(cfg).get(row["pdf_path"].replace(".pdf", ".md")).decode()
    assert "FOR EDUCATIONAL PURPOSES ONLY" in md and "Underweight" not in md
    assert sent[0][0] == "buyer@test" and sent[0][2][0].endswith(".pdf")


def test_advice_is_fixed_by_the_editor(env):
    _cfg, engine, _sent, make = env
    order = _paid(engine)
    llm = FakeLLM(advice_rounds=1)
    assert pipeline.process(order, make(llm)) == "delivered"
    assert json.loads(db.get(engine, order["id"])["qc_report"])["fix_rounds"] == 1
    assert any("Contains advice language" in c for c in llm.calls)       # the fix round was told what to fix


def test_persistent_problems_are_held_not_sent(env):
    cfg, engine, sent, make = env
    order = _paid(engine)
    assert pipeline.process(order, make(FakeLLM(advice_rounds=99))) == "held"
    assert db.get(engine, order["id"])["status"] == "held"
    recipients = [s[0] for s in sent]
    assert "buyer@test" in recipients and "oi@test" in recipients
    assert all(att is None for to, _s, att in sent if to == "buyer@test")  # the customer never gets the PDF


def test_reviewer_rejection_holds(env):
    _cfg, engine, _sent, make = env
    assert pipeline.process(_paid(engine), make(FakeLLM(reviewer="fail"))) == "held"


def test_pdf_scan_failure_holds(env):
    _cfg, engine, _sent, make = env
    assert pipeline.process(_paid(engine), make(FakeLLM(), pdf_problems=["missing disclaimer"])) == "held"


def test_errors_retry_then_refund(env):
    _cfg, engine, sent, make = env
    def boom(*a):
        raise RuntimeError("DeepSeek timeout")
    d = make(FakeLLM(), run=boom)
    order = _paid(engine)
    assert pipeline.process(order, d) == "queued"                   # first failure: retried
    again = db.claim_next(engine)
    assert pipeline.process(again, d) == "refunded"                 # second failure: refunded
    assert "refund" in sent[0][1].lower()


# ---------------------------------------------------------------- market facts

def test_market_facts_crypto_open_candle():
    dates = pd.date_range(end="2026-11-02", periods=260, freq="D")
    df = pd.DataFrame({"Date": dates, "Open": 1.0, "High": 2.0, "Low": 0.5, "Close": [100.0 + i for i in range(260)],
                       "Volume": 1})
    f = market_facts.compute("BTC-USD", "2026-11-02", "crypto", loader=lambda *a, **k: df.copy(),
                             now_utc=pd.Timestamp("2026-11-02 18:55"))
    assert f["live_price"] == 359.0 and f["last_close_date"] == "2026-11-01"
    notes = market_facts.report_notes(f, [], "s")
    assert notes["price_label"] == "Price at report time" and "not a daily close" in notes["price_note"]
    assert f["trend_value"] == "Above 200-day average"


# ---------------------------------------------------------------- web

class FakeSession:
    id, url = "cs_test_1", "https://checkout.stripe.test/cs_test_1"


def _sign(payload: bytes, secret: str) -> str:
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={ts},v1={sig}"


@pytest.fixture
def client(env):
    from fastapi.testclient import TestClient

    from blmi_store import payments
    from blmi_store.web import create_app

    cfg, engine, sent, _make = env
    def validate(s):
        if s.upper().startswith("BTC"):
            return {"ok": True, "symbol": "BTC-USD", "name": "Bitcoin USD", "asset_type": "crypto"}
        return {"ok": False, "error": "Unknown symbol."}
    app = create_app(cfg=cfg, engine=engine, validate=validate, checkout=lambda *a: FakeSession(),
                     verify=payments.verify_webhook, send_email=lambda *a: sent.append(a) or True,
                     refund=lambda *a: True)
    return TestClient(app), cfg, engine, sent


def test_checkout_requires_consent_and_valid_symbol(client):
    c, *_ = client
    base = {"ticker": "BTC-USD", "tier": "deep", "email": "a@b.co", "consent": True}
    assert c.post("/api/checkout", json={**base, "consent": False}).status_code == 400
    assert c.post("/api/checkout", json={**base, "ticker": "ZZZZ"}).status_code == 400
    assert c.post("/api/checkout", json={**base, "email": "nope"}).status_code == 400
    r = c.post("/api/checkout", json=base)
    assert r.status_code == 200 and r.json()["url"].startswith("https://checkout.stripe.test")


def test_webhook_queues_paid_order_once(client):
    c, cfg, engine, _sent = client
    c.post("/api/checkout", json={"ticker": "BTC-USD", "tier": "quick", "email": "a@b.co", "consent": True})
    order = db.by_session(engine, "cs_test_1")
    event = {"id": "evt_1", "object": "event", "type": "checkout.session.completed",
             "data": {"object": {"id": "cs_test_1", "object": "checkout.session", "payment_status": "paid",
                                 "payment_intent": "pi_9", "metadata": {"order_id": order["id"]}}}}
    payload = json.dumps(event).encode()
    assert c.post("/api/stripe/webhook", content=payload, headers={"stripe-signature": "bad"}).status_code == 400
    for _ in range(2):   # Stripe may deliver twice
        r = c.post("/api/stripe/webhook", content=payload, headers={"stripe-signature": _sign(payload, cfg.stripe_webhook_secret)})
        assert r.status_code == 200
    row = db.get(engine, order["id"])
    assert row["status"] == "queued" and row["stripe_payment_intent"] == "pi_9" and row["analysis_date"]
    status = c.get(f"/api/order/{order['id']}?t={order['token']}").json()
    assert status["status"] == "queued"
    assert c.get(f"/api/order/{order['id']}?t=wrong").status_code == 404


def test_download_and_admin_release(client, tmp_path):
    c, cfg, engine, sent = client
    o = db.create_order(engine, email="a@b.co", ticker="BTC-USD", asset_type="crypto", tier="deep",
                        amount_cents=2900, consent_text="c", consent_ip=None)
    Storage(cfg).put(f"{o['id']}/r.pdf", b"%PDF-1.7 test")
    db.set_fields(engine, o["id"], status="held", pdf_path=f"{o['id']}/r.pdf")
    assert c.get(f"/download/{o['id']}?t={o['token']}").status_code == 404      # held reports can't be downloaded
    assert c.get("/admin/api/orders").status_code == 401
    assert c.get("/admin?key=k", follow_redirects=False).status_code == 303     # sets a secure cookie on https
    assert c.post(f"/admin/api/orders/{o['id']}/release", headers={"x-admin-key": "k"}).status_code == 200
    r = c.get(f"/download/{o['id']}?t={o['token']}")
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert sent and sent[-1][1] == "a@b.co"


def test_pages_render(client):
    c, *_ = client
    for path in ("/", "/terms", "/static/blmi-icon.png", "/api/config", "/healthz"):
        assert c.get(path).status_code == 200, path
    assert "Not investment advice" in c.get("/").text or "Not investment advice" in c.get("/").text.title()


# ---------------------------------------------------------------- the real PDF

def test_educational_pdf_renders_and_passes_scan(tmp_path):
    from tradingagents.report_pdf import find_browser, write_pdf

    if not find_browser():
        pytest.skip("no Chromium-based browser")
    report = editor.EditedReport(
        sections={"market": "Price is **76,891.44** at report time, 5.10% above the 200-day average.\n\n"
                            "| Layer | Level |\n|---|---|\n| 200-day SMA | 73,157.59 |",
                  "evidence": "### Data pointing to strength\n- Above the 200-day average.\n\n"
                              "### Data pointing to weakness\n- ETF outflows of $643.3M."},
        summary="Price is above its long-term average and below its medium-term average.",
        levels="| Level | What it is | Why analysts watch it |\n|---|---|---|\n| 73,157.59 | 200-day SMA | Long-term trend |",
        gaps=["News: no report was produced in this run."])
    notes = market_facts.report_notes(FACTS_DICT, report.gaps, report.summary)
    ok, pdf = write_pdf("BTC-USD", {"trade_date": "2026-11-02", "asset_type": "crypto"},
                        {"edition": "educational", "report_notes": notes, "analysts": ["market"]},
                        report.parts(), tmp_path)
    assert ok, pdf
    assert qc.check_pdf(pdf) == []
    import pymupdf
    text = " ".join(p.get_text() for p in pymupdf.open(pdf))
    assert "Underweight" not in text and "PRICE TARGET" not in text and "TIME HORIZON" not in text
    assert "$76,891.44" in text and "About this report" in text
