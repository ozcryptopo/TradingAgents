"""Storefront, checkout, Stripe webhook, order status, downloads and admin.

Run: uvicorn blmi_store.web:app --host 0.0.0.0 --port $PORT
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles

from blmi_store import db, delivery, payments, pipeline, tickers
from blmi_store.config import STATIC_DIR, settings

log = logging.getLogger(__name__)
PAGES = Path(__file__).parent / "pages"
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,255}\.[^@\s]{2,}$")
CONSENT_TEXT = ("I understand this report is educational research describing market conditions. It is not "
                "investment advice and does not tell me to buy, sell or hold anything. I am responsible for my own "
                "decisions.")


def create_app(cfg=None, engine=None, validate=tickers.validate, checkout=payments.create_checkout,
               verify=payments.verify_webhook, storage=None, send_email=delivery.send_email,
               refund=payments.refund) -> FastAPI:
    cfg = cfg or settings()
    engine = engine or db.make_engine(cfg.database_url)
    storage = storage or delivery.Storage(cfg)
    app = FastAPI(title="BrightLaunch Market Intelligence", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def page(name: str) -> HTMLResponse:
        return HTMLResponse((PAGES / name).read_text(encoding="utf-8"))

    def order_for(order_id: str, token: str | None) -> dict:
        order = db.get(engine, order_id)
        if not order or not token or not secrets.compare_digest(order["token"], token):
            raise HTTPException(404, "Order not found")
        return order

    def is_admin(request: Request) -> bool:
        key = request.cookies.get("blmi_admin") or request.headers.get("x-admin-key") or ""
        return bool(cfg.admin_key) and secrets.compare_digest(key, cfg.admin_key)

    @app.get("/", response_class=HTMLResponse)
    def home():
        return page("index.html")

    @app.get("/terms", response_class=HTMLResponse)
    def terms():
        return page("terms.html")

    @app.get("/healthz")
    def health():
        return {"ok": True}

    @app.get("/api/config")
    def config():
        return {"tiers": [{"key": t.key, "name": t.name, "price": t.price_cents / 100, "eta": t.eta,
                           "blurb": t.blurb, "analysts": len(t.analysts)} for t in cfg.tiers.values()],
                "consent": CONSENT_TEXT}

    @app.get("/api/ticker")
    def ticker(symbol: str = ""):
        return validate(symbol)

    @app.post("/api/checkout")
    async def start_checkout(request: Request):
        body = await request.json()
        email = str(body.get("email", "")).strip()
        tier = cfg.tiers.get(str(body.get("tier", "")))
        if not EMAIL.match(email):
            raise HTTPException(400, "Enter a valid email address.")
        if not tier:
            raise HTTPException(400, "Choose a report type.")
        if body.get("consent") is not True:
            raise HTTPException(400, "Please confirm you understand the report is not investment advice.")
        found = validate(str(body.get("ticker", "")))
        if not found.get("ok"):
            raise HTTPException(400, found.get("error", "Unknown symbol."))
        ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "").split(",")[0]
        order = db.create_order(engine, email=email, ticker=found["symbol"], asset_type=found["asset_type"],
                                tier=tier.key, amount_cents=tier.price_cents, consent_text=CONSENT_TEXT,
                                consent_ip=ip[:64])
        session = checkout(cfg, order, tier)
        db.set_fields(engine, order["id"], stripe_session_id=session.id)
        return {"url": session.url}

    @app.post("/api/stripe/webhook")
    async def stripe_webhook(request: Request):
        payload = await request.body()
        try:
            event = verify(cfg, payload, request.headers.get("stripe-signature", ""))
        except Exception:  # noqa: BLE001 - bad signature or payload
            raise HTTPException(400, "Invalid signature")
        kind = event["type"]
        session = event["data"]["object"]
        session = session.to_dict() if hasattr(session, "to_dict") else dict(session)
        order_id = (session.get("metadata") or {}).get("order_id") or session.get("client_reference_id")
        order = db.get(engine, order_id) if order_id else None
        if not order:
            return {"ignored": True}
        if kind in ("checkout.session.completed", "checkout.session.async_payment_succeeded") \
                and session.get("payment_status") == "paid":
            if db.transition(engine, order["id"], "pending_payment", "queued",
                             stripe_payment_intent=session.get("payment_intent"),
                             analysis_date=tickers.analysis_date(order["asset_type"]), stage="Paid; in the queue"):
                log.info("Order %s paid and queued", order["id"])
        elif kind == "checkout.session.expired":
            db.transition(engine, order["id"], "pending_payment", "expired")
        return {"received": True}

    @app.get("/order/{order_id}", response_class=HTMLResponse)
    def order_page(order_id: str, t: str = ""):
        order_for(order_id, t)
        return page("order.html")

    @app.get("/api/order/{order_id}")
    def order_status(order_id: str, t: str = ""):
        o = order_for(order_id, t)
        return {"ticker": o["ticker"], "tier": cfg.tiers[o["tier"]].name, "status": o["status"],
                "stage": o["stage"], "email": o["email"], "eta": cfg.tiers[o["tier"]].eta,
                "download": f"/download/{o['id']}?t={o['token']}" if o["status"] == "delivered" else None}

    @app.get("/download/{order_id}")
    def download(order_id: str, t: str = ""):
        o = order_for(order_id, t)
        if o["status"] != "delivered" or not o["pdf_path"]:
            raise HTTPException(404, "This report isn't ready yet.")
        age = db.now() - o["delivered_at"].replace(tzinfo=o["delivered_at"].tzinfo or db.now().tzinfo)
        if age.days > 30:
            raise HTTPException(410, "This download link has expired. Reply to your delivery email for a copy.")
        return Response(storage.get(o["pdf_path"]), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{Path(o["pdf_path"]).name}"'})

    # ---- admin -------------------------------------------------------------------------------------------
    @app.get("/admin", response_class=HTMLResponse)
    def admin(request: Request, key: str = ""):
        if key and cfg.admin_key and secrets.compare_digest(key, cfg.admin_key):
            resp = RedirectResponse("/admin", status_code=303)
            resp.set_cookie("blmi_admin", key, httponly=True, secure=cfg.base_url.startswith("https"),
                            samesite="strict", max_age=60 * 60 * 24 * 30)
            return resp
        if not is_admin(request):
            return HTMLResponse("<p>Add ?key=YOUR_ADMIN_KEY to the address to sign in.</p>", status_code=401)
        return page("admin.html")

    @app.get("/admin/api/orders")
    def admin_orders(request: Request):
        if not is_admin(request):
            raise HTTPException(401)
        rows = db.recent(engine)
        for r in rows:
            r["qc_report"] = json.loads(r["qc_report"]) if r.get("qc_report") else None
            for k in ("created_at", "updated_at", "delivered_at"):
                r[k] = r[k].isoformat() if r.get(k) else None
            r.pop("token", None)
        return rows

    @app.get("/admin/api/orders/{order_id}/pdf")
    def admin_pdf(order_id: str, request: Request):
        if not is_admin(request):
            raise HTTPException(401)
        o = db.get(engine, order_id)
        if not o or not o["pdf_path"]:
            raise HTTPException(404)
        return Response(storage.get(o["pdf_path"]), media_type="application/pdf")

    @app.post("/admin/api/orders/{order_id}/{action}")
    def admin_action(order_id: str, action: str, request: Request):
        if not is_admin(request):
            raise HTTPException(401)
        o = db.get(engine, order_id)
        if not o:
            raise HTTPException(404)
        if action == "release" and o["status"] == "held":
            db.set_fields(engine, o["id"], status="delivered", delivered_at=db.now(), stage="Delivered after review")
            pdf = storage.get(o["pdf_path"])
            subject, html = delivery.delivered_email(o, pipeline.download_link(cfg, o))
            send_email(cfg, o["email"], subject, html, (Path(o["pdf_path"]).name, pdf))
        elif action == "rerun" and o["status"] in ("held", "failed"):
            db.set_fields(engine, o["id"], status="queued", attempts=0, stage="Re-run requested", error=None,
                          analysis_date=tickers.analysis_date(o["asset_type"]))
        elif action == "refund" and o["status"] in ("held", "failed", "queued"):
            refund(cfg, o["stripe_payment_intent"])
            db.set_fields(engine, o["id"], status="refunded", stage="Refunded")
            subject, html = delivery.failed_email(o)
            send_email(cfg, o["email"], subject, html, None)
        else:
            raise HTTPException(400, f"Can't {action} an order that is {o['status']}.")
        return {"ok": True}

    @app.get("/favicon.ico")
    def favicon():
        return FileResponse(STATIC_DIR / "blmi-icon.png")

    return app


def _lazy_app():
    return create_app()


class _App:
    """Build the app on first request so importing this module needs no environment."""
    _app = None

    async def __call__(self, scope, receive, send):
        if _App._app is None:
            _App._app = _lazy_app()
        await _App._app(scope, receive, send)


app = _App()
