"""Orders table and the job queue (Postgres in production, SQLite for local runs and tests)."""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import (Column, DateTime, Integer, MetaData, String, Table, Text, create_engine, select,
                        update)
from sqlalchemy.engine import Engine

metadata = MetaData()

# Status flow: pending_payment -> queued -> running -> delivered
#              (or held: QC failed, waiting for review; failed: refunded; expired: checkout abandoned)
STATUSES = ("pending_payment", "queued", "running", "delivered", "held", "failed", "refunded", "expired")

orders = Table(
    "orders", metadata,
    Column("id", String(36), primary_key=True),
    Column("token", String(64), nullable=False),          # secret in the buyer's status/download links
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("email", String(320), nullable=False),
    Column("ticker", String(32), nullable=False),
    Column("asset_type", String(16), nullable=False),
    Column("tier", String(16), nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("status", String(24), nullable=False, index=True),
    Column("stage", String(64)),                          # what the worker is doing now, for the status page
    Column("stripe_session_id", String(255), index=True),
    Column("stripe_payment_intent", String(255)),
    Column("analysis_date", String(10)),
    Column("attempts", Integer, nullable=False, default=0),
    Column("qc_report", Text),                            # JSON from the quality-control agent
    Column("error", Text),
    Column("pdf_path", String(512)),
    Column("consent_text", Text),
    Column("consent_ip", String(64)),
    Column("delivered_at", DateTime(timezone=True)),
)


def now() -> datetime:
    return datetime.now(timezone.utc)


def make_engine(url: str) -> Engine:
    if url.startswith("postgres://"):           # Supabase/Railway style URLs
        url = "postgresql+psycopg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    engine = create_engine(url, pool_pre_ping=True, future=True)
    metadata.create_all(engine)
    return engine


def create_order(engine: Engine, *, email: str, ticker: str, asset_type: str, tier: str, amount_cents: int,
                 consent_text: str, consent_ip: str | None) -> dict:
    row = dict(id=str(uuid.uuid4()), token=secrets.token_urlsafe(24), created_at=now(), updated_at=now(),
               email=email, ticker=ticker, asset_type=asset_type, tier=tier, amount_cents=amount_cents,
               status="pending_payment", attempts=0, consent_text=consent_text, consent_ip=consent_ip)
    with engine.begin() as c:
        c.execute(orders.insert().values(**row))
    return row


def get(engine: Engine, order_id: str) -> dict | None:
    with engine.connect() as c:
        r = c.execute(select(orders).where(orders.c.id == order_id)).mappings().first()
    return dict(r) if r else None


def by_session(engine: Engine, session_id: str) -> dict | None:
    with engine.connect() as c:
        r = c.execute(select(orders).where(orders.c.stripe_session_id == session_id)).mappings().first()
    return dict(r) if r else None


def set_fields(engine: Engine, order_id: str, **fields) -> None:
    if "qc_report" in fields and not isinstance(fields["qc_report"], (str, type(None))):
        fields["qc_report"] = json.dumps(fields["qc_report"])
    with engine.begin() as c:
        c.execute(update(orders).where(orders.c.id == order_id).values(updated_at=now(), **fields))


def transition(engine: Engine, order_id: str, from_status: str, to_status: str, **fields) -> bool:
    """Move an order only if it is still in ``from_status`` (makes webhooks idempotent)."""
    with engine.begin() as c:
        res = c.execute(update(orders).where(orders.c.id == order_id, orders.c.status == from_status)
                        .values(status=to_status, updated_at=now(), **fields))
    return res.rowcount == 1


def claim_next(engine: Engine) -> dict | None:
    """Atomically take the oldest queued order; safe with several workers on Postgres."""
    with engine.begin() as c:
        q = select(orders.c.id).where(orders.c.status == "queued").order_by(orders.c.created_at).limit(1)
        if engine.dialect.name == "postgresql":
            q = q.with_for_update(skip_locked=True)
        order_id = c.execute(q).scalar()
        if not order_id:
            return None
        c.execute(update(orders).where(orders.c.id == order_id, orders.c.status == "queued")
                  .values(status="running", stage="Starting", attempts=orders.c.attempts + 1, updated_at=now()))
        r = c.execute(select(orders).where(orders.c.id == order_id)).mappings().first()
    return dict(r)


def recover_stuck(engine: Engine, max_attempts: int, older_than: timedelta = timedelta(hours=2)) -> list[dict]:
    """Requeue runs whose worker died mid-run; return those that are out of attempts."""
    cutoff = now() - older_than
    out_of_attempts = []
    with engine.begin() as c:
        rows = c.execute(select(orders).where(orders.c.status == "running", orders.c.updated_at < cutoff)
                         ).mappings().all()
        for r in rows:
            if r["attempts"] < max_attempts:
                c.execute(update(orders).where(orders.c.id == r["id"]).values(status="queued", updated_at=now(),
                                                                             stage="Retrying"))
            else:
                out_of_attempts.append(dict(r))
    return out_of_attempts


def recent(engine: Engine, limit: int = 200) -> list[dict]:
    with engine.connect() as c:
        rows = c.execute(select(orders).order_by(orders.c.created_at.desc()).limit(limit)).mappings().all()
    return [dict(r) for r in rows]
