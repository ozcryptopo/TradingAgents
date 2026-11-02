"""Stripe Checkout and refunds."""

from __future__ import annotations

import stripe

from blmi_store.config import Settings, Tier


def _client(cfg: Settings) -> stripe.StripeClient:
    if not cfg.stripe_secret_key:
        raise RuntimeError("STRIPE_SECRET_KEY is not set")
    return stripe.StripeClient(cfg.stripe_secret_key)


def create_checkout(cfg: Settings, order: dict, tier: Tier) -> stripe.checkout.Session:
    status_url = f"{cfg.base_url}/order/{order['id']}?t={order['token']}"
    return _client(cfg).v1.checkout.sessions.create(params={
        "mode": "payment",
        "customer_email": order["email"],
        "client_reference_id": order["id"],
        "line_items": [{
            "quantity": 1,
            "price_data": {
                "currency": "usd",
                "unit_amount": tier.price_cents,
                "product_data": {
                    "name": f"{order['ticker']} Market Conditions Report ({tier.name})",
                    "description": "Educational, facts-only report on current market conditions. Not investment advice.",
                },
            },
        }],
        "metadata": {"order_id": order["id"], "ticker": order["ticker"], "tier": tier.key},
        "payment_intent_data": {"metadata": {"order_id": order["id"]}},
        "custom_text": {"submit": {"message": "Educational research only. This report describes market conditions "
                                              "and does not tell you to buy or sell anything."}},
        "success_url": status_url + "&paid=1",
        "cancel_url": f"{cfg.base_url}/?canceled=1",
    })


def verify_webhook(cfg: Settings, payload: bytes, signature: str) -> stripe.Event:
    return stripe.Webhook.construct_event(payload, signature, cfg.stripe_webhook_secret)


def refund(cfg: Settings, payment_intent: str | None) -> bool:
    if not payment_intent:
        return False
    _client(cfg).v1.refunds.create(params={"payment_intent": payment_intent})
    return True
