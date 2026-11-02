"""The report worker: `python -m blmi_store.worker`."""

from __future__ import annotations

import logging
import time

from blmi_store import db, delivery, market_facts, payments, pipeline, qc
from blmi_store.config import apply_report_branding, settings
from blmi_store.llm import build_llm

log = logging.getLogger("blmi_store.worker")


def build_deps() -> pipeline.Deps:
    from blmi_store.runner import run_analysis

    cfg = settings()
    apply_report_branding(cfg)
    return pipeline.Deps(
        cfg=cfg, engine=db.make_engine(cfg.database_url), llm=build_llm(), run_analysis=run_analysis,
        compute_facts=market_facts.compute, render_pdf=pipeline.default_render, check_pdf=qc.check_pdf,
        storage=delivery.Storage(cfg), send_email=delivery.send_email, refund=payments.refund,
    )


def run_once(d: pipeline.Deps) -> str | None:
    for order in db.recover_stuck(d.engine, d.cfg.max_attempts):
        pipeline.fail_and_refund(d, order, "The worker stopped during every attempt.")
    order = db.claim_next(d.engine)
    if not order:
        return None
    log.info("Processing order %s: %s (%s)", order["id"], order["ticker"], order["tier"])
    return pipeline.process(order, d)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    d = build_deps()
    log.info("BLMI report worker started")
    while True:
        try:
            if run_once(d) is None:
                time.sleep(d.cfg.poll_seconds)
        except Exception:  # noqa: BLE001 - keep the worker alive; the order itself is retried or refunded
            log.exception("Worker loop error")
            time.sleep(d.cfg.poll_seconds)


if __name__ == "__main__":
    main()
