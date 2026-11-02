"""Where finished PDFs are kept, and the emails that go out."""

from __future__ import annotations

import base64
import logging
from html import escape
from pathlib import Path

import httpx

from blmi_store.config import Settings

log = logging.getLogger(__name__)


class Storage:
    """Supabase Storage (private bucket) when configured, otherwise a local folder (a Railway volume)."""

    def __init__(self, cfg: Settings):
        self.cfg = cfg

    @property
    def remote(self) -> bool:
        return bool(self.cfg.supabase_url and self.cfg.supabase_service_key)

    def _url(self, path: str) -> str:
        return f"{self.cfg.supabase_url}/storage/v1/object/{self.cfg.supabase_bucket}/{path}"

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.cfg.supabase_service_key}", "apikey": self.cfg.supabase_service_key}

    def put(self, path: str, data: bytes) -> str:
        if self.remote:
            r = httpx.post(self._url(path), content=data, timeout=60,
                           headers={**self._headers(), "Content-Type": "application/pdf", "x-upsert": "true"})
            r.raise_for_status()
        else:
            target = Path(self.cfg.local_storage_dir) / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        return path

    def get(self, path: str) -> bytes:
        if self.remote:
            r = httpx.get(self._url(path), headers=self._headers(), timeout=60)
            r.raise_for_status()
            return r.content
        return (Path(self.cfg.local_storage_dir) / path).read_bytes()


def send_email(cfg: Settings, to: str, subject: str, html: str, attachment: tuple[str, bytes] | None = None) -> bool:
    if not cfg.resend_api_key:
        log.warning("RESEND_API_KEY not set; email to %s not sent: %s", to, subject)
        return False
    payload = {"from": cfg.email_from, "to": [to], "subject": subject, "html": html}
    if attachment:
        payload["attachments"] = [{"filename": attachment[0], "content": base64.b64encode(attachment[1]).decode()}]
    try:
        r = httpx.post("https://api.resend.com/emails", json=payload, timeout=30,
                       headers={"Authorization": f"Bearer {cfg.resend_api_key}"})
        r.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.error("Email to %s failed: %s", to, exc)
        return False


def _wrap(body: str) -> str:
    return f"""<div style="font-family:Inter,Helvetica,Arial,sans-serif;max-width:560px;margin:auto;color:#111827">
<div style="background:#0b1e3f;color:#fff;padding:18px 22px;border-radius:10px 10px 0 0">
<b style="color:#ffd166;letter-spacing:.06em">BRIGHTLAUNCH</b> <span style="color:#fff">Market Intelligence</span></div>
<div style="border:1px solid #e5e7eb;border-top:0;padding:22px;border-radius:0 0 10px 10px;line-height:1.55">{body}
<p style="font-size:12px;color:#6b7280;margin-top:22px">For educational purposes only. Not investment advice.
BrightLaunch Market Intelligence describes market conditions; it does not recommend buying or selling anything.</p>
</div></div>"""


def delivered_email(order: dict, link: str) -> tuple[str, str]:
    t = escape(order["ticker"])
    return (f"Your {order['ticker']} market conditions report is ready",
            _wrap(f"<p>Your {t} market conditions report is attached and ready to download.</p>"
                  f"<p><a href=\"{escape(link)}\" style=\"background:#f4811e;color:#fff;padding:10px 18px;"
                  f"border-radius:6px;text-decoration:none;font-weight:600\">Download your report</a></p>"
                  f"<p>The link works for 30 days. Questions? Just reply to this email.</p>"))


def delayed_email(order: dict, link: str) -> tuple[str, str]:
    t = escape(order["ticker"])
    return (f"Your {order['ticker']} report needs a little more time",
            _wrap(f"<p>Our quality check flagged something in your {t} report, so a person is reviewing it before "
                  f"it is sent. You'll get it within 24 hours, or a full refund.</p>"
                  f"<p><a href=\"{escape(link)}\">Check your order status</a></p>"))


def failed_email(order: dict) -> tuple[str, str]:
    t = escape(order["ticker"])
    return (f"We couldn't produce your {order['ticker']} report: refund issued",
            _wrap(f"<p>We weren't able to produce a reliable {t} report this time, so we've refunded your payment "
                  f"in full. Refunds usually appear within 5-10 business days.</p>"))


def admin_email(order: dict, what: str, details: str, admin_link: str) -> tuple[str, str]:
    return (f"[BLMI store] {what}: {order['ticker']} ({order['tier']}) order {order['id'][:8]}",
            _wrap(f"<p><b>{escape(what)}</b> for {escape(order['ticker'])}, {escape(order['tier'])} tier, "
                  f"customer {escape(order['email'])}.</p><pre style=\"white-space:pre-wrap;font-size:12px;"
                  f"background:#f6f7f9;padding:10px;border-radius:6px\">{escape(details[:6000])}</pre>"
                  f"<p><a href=\"{escape(admin_link)}\">Open the admin page</a></p>"))
