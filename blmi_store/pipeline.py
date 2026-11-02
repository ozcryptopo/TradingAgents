"""One paid order, start to finish: run, edit to facts only, quality-check, render, deliver."""

from __future__ import annotations

import json
import logging
import shutil
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from blmi_store import db, delivery, market_facts, qc
from blmi_store.config import Settings
from blmi_store.editor import EditedReport, apply_fixes, edit_report
from blmi_store.llm import LLMCall

log = logging.getLogger(__name__)


@dataclass
class Deps:
    """Everything the pipeline touches, so tests can swap in fakes."""
    cfg: Settings
    engine: object
    llm: LLMCall
    run_analysis: Callable           # (ticker, asset_type, date, tier) -> (final_state, settings)
    compute_facts: Callable          # (ticker, date, asset_type) -> facts
    render_pdf: Callable             # (ticker, state, settings, parts, out_dir) -> (ok, path_or_message)
    check_pdf: Callable              # (pdf_path) -> [problems]
    storage: delivery.Storage
    send_email: Callable             # (cfg, to, subject, html, attachment) -> bool
    refund: Callable                 # (cfg, payment_intent) -> bool


def default_render(ticker, state, settings, parts, out_dir):
    from tradingagents.report_pdf import write_pdf

    return write_pdf(ticker, state, settings, parts, Path(out_dir))


def status_link(cfg: Settings, order: dict) -> str:
    return f"{cfg.base_url}/order/{order['id']}?t={order['token']}"


def download_link(cfg: Settings, order: dict) -> str:
    return f"{cfg.base_url}/download/{order['id']}?t={order['token']}"


def report_markdown(order: dict, edited: EditedReport, notes: dict) -> str:
    """The finished report as Markdown, kept beside the PDF for agents and for review."""
    lines = [f"# {order['ticker']} Market Conditions Report", "",
             "> **FOR EDUCATIONAL PURPOSES ONLY. NOT INVESTMENT ADVICE.** BrightLaunch Market Intelligence describes "
             "market conditions; it does not recommend buying or selling anything.", "",
             f"- {notes['price_label']}: {notes['price_value']} ({notes['price_note']})",
             f"- {notes['trend_label']}: {notes['trend_value']} ({notes['trend_note']})", ""]
    if notes.get("timing_note"):
        lines += [notes["timing_note"], ""]
    for heading, _folder, items in edited.parts():
        lines += [f"## {heading}", ""]
        for title, _file, text in items:
            lines += [f"### {title}", "", text, ""]
    return "\n".join(lines)


def process(order: dict, d: Deps) -> str:
    """Process a claimed order; returns its final status."""
    cfg, engine = d.cfg, d.engine
    tier = cfg.tiers[order["tier"]]
    work = Path(cfg.work_dir) / order["id"]
    work.mkdir(parents=True, exist_ok=True)
    stage = lambda text: db.set_fields(engine, order["id"], stage=text)  # noqa: E731
    try:
        date = order["analysis_date"]
        stage(f"Running {len(tier.analysts)} analysts and the research debate")
        state, run_settings = d.run_analysis(order["ticker"], order["asset_type"], date, tier)
        stage("Checking prices against market data")
        facts = d.compute_facts(order["ticker"], date, order["asset_type"])
        facts_text = market_facts.facts_text(facts)
        stage("Editing the report to facts only")
        edited = edit_report(d.llm, state, facts_text)
        result = qc.review(d.llm, edited, state, facts, facts_text)
        rounds = 0
        while not result.passed and rounds < cfg.qc_fix_rounds:
            rounds += 1
            stage(f"Quality check found issues; fixing (round {rounds})")
            edited = apply_fixes(d.llm, edited, state, facts_text, result.issues)
            result = qc.review(d.llm, edited, state, facts, facts_text)

        stage("Building the PDF")
        notes = market_facts.report_notes(facts, edited.gaps, edited.summary)
        render_state = {"trade_date": date, "asset_type": order["asset_type"]}   # no decision, so no rating
        render_settings = {**run_settings, "edition": "educational", "report_notes": notes}
        ok, pdf = d.render_pdf(order["ticker"], render_state, render_settings, edited.parts(), work)
        if not ok:
            raise RuntimeError(f"PDF render failed: {pdf}")
        pdf_problems = d.check_pdf(pdf)
        if pdf_problems:
            result.passed = False
            for p in pdf_problems:
                result.add("pdf", p)

        base = f"{order['id']}/BLMI_{order['ticker'].replace('/', '-')}_{date}"
        pdf_bytes = Path(pdf).read_bytes()
        d.storage.put(f"{base}.pdf", pdf_bytes)
        d.storage.put(f"{base}.md", report_markdown(order, edited, notes).encode())
        report = {**result.as_dict(), "fix_rounds": rounds, "gaps": edited.gaps}

        if result.passed:
            stage("Delivered")
            db.set_fields(engine, order["id"], status="delivered", pdf_path=f"{base}.pdf", qc_report=report,
                          delivered_at=db.now(), error=None)
            subject, html = delivery.delivered_email(order, download_link(cfg, order))
            d.send_email(cfg, order["email"], subject, html, (Path(base).name + ".pdf", pdf_bytes))
            return "delivered"

        stage("Held for review")
        db.set_fields(engine, order["id"], status="held", pdf_path=f"{base}.pdf", qc_report=report)
        subject, html = delivery.delayed_email(order, status_link(cfg, order))
        d.send_email(cfg, order["email"], subject, html, None)
        if cfg.admin_email:
            subject, html = delivery.admin_email(order, "Report held by quality control",
                                                 json.dumps(result.issues, indent=2), f"{cfg.base_url}/admin")
            d.send_email(cfg, cfg.admin_email, subject, html, ("held-report.pdf", pdf_bytes))
        return "held"
    except Exception as exc:  # noqa: BLE001 - every failure must end in a retry or a refund
        log.exception("Order %s failed", order["id"])
        detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-3000:]}"
        latest = db.get(engine, order["id"]) or order
        if latest["attempts"] < cfg.max_attempts:
            db.set_fields(engine, order["id"], status="queued", stage="Retrying after an error", error=detail)
            return "queued"
        return fail_and_refund(d, latest, detail)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def fail_and_refund(d: Deps, order: dict, detail: str) -> str:
    cfg = d.cfg
    refunded = False
    try:
        refunded = d.refund(cfg, order.get("stripe_payment_intent"))
    except Exception as exc:  # noqa: BLE001
        detail += f"\nRefund failed: {exc}"
    status = "refunded" if refunded else "failed"
    db.set_fields(d.engine, order["id"], status=status, stage="Could not be completed", error=detail)
    if refunded:
        subject, html = delivery.failed_email(order)
        d.send_email(cfg, order["email"], subject, html, None)
    if cfg.admin_email:
        subject, html = delivery.admin_email(order, f"Order {status}", detail, f"{cfg.base_url}/admin")
        d.send_email(cfg, cfg.admin_email, subject, html, None)
    return status
