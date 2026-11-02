"""The editing agent: turn a TradingAgents run into a facts-only market conditions report.

Nothing a customer receives may contain investment advice. The trader, risk and
portfolio manager outputs (ratings, targets, sizing, hedges) are never shown; the
analyst reports and the bull/bear debate are rewritten as a factual description
of market conditions; and the summary and key levels are written from the
rewritten, already-factual sections only, so advice cannot leak in from the
decision agents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from blmi_store.llm import LLMCall

SPEC_PATH = Path(__file__).with_name("REPORT_SPEC.md")


def spec() -> str:
    """The report specification every agent works from (REPORT_SPEC.md)."""
    return SPEC_PATH.read_text(encoding="utf-8")


def editor_system() -> str:
    return (spec() + "\n\n---\n\nYOUR ROLE: you are the BLMI editing agent. Rewrite the SOURCE TEXT you are given "
            "as the requested section of a BLMI report, following the specification above exactly: facts only, "
            "no advice, numbers copied exactly, formatting per section 5. Output only the section's Markdown.")

SECTIONS = (
    # (key, title, part, state paths)
    ("market", "Price, trend and momentum", "I. Market Conditions", [("market_report",)]),
    ("sentiment", "Sentiment", "I. Market Conditions", [("sentiment_report",)]),
    ("news", "News and macro", "I. Market Conditions", [("news_report",)]),
    ("fundamentals", "Fundamentals, flows and positioning", "I. Market Conditions", [("fundamentals_report",)]),
    ("evidence", "Evidence on both sides", "II. Evidence on Both Sides",
     [("investment_debate_state", "bull_history"), ("investment_debate_state", "bear_history")]),
)

_UNAVAILABLE = re.compile(r"\b(unavailable|no data (was )?returned|could not be retrieved|data (is )?missing|"
                          r"no (news|articles) (were )?found|failed to (load|fetch))\b", re.I)


@dataclass
class EditedReport:
    sections: dict[str, str] = field(default_factory=dict)   # key -> markdown
    summary: str = ""
    levels: str = ""
    gaps: list[str] = field(default_factory=list)

    def parts(self) -> list[tuple[str, str, list[tuple[str, str, str]]]]:
        """In the shape the PDF renderer expects: (heading, folder, [(title, file, text)])."""
        grouped: dict[str, list] = {}
        for key, title, part, _paths in SECTIONS:
            if self.sections.get(key):
                grouped.setdefault(part, []).append((title, f"{key}.md", self.sections[key]))
        out = [(part, part, items) for part, items in grouped.items()]
        tail = []
        if self.levels:
            tail.append(("Levels the data highlights", "levels.md", self.levels))
        if self.summary:
            tail.append(("Market conditions summary", "summary.md", self.summary))
        if tail:
            out.append(("III. Summary and Key Levels", "summary", tail))
        return out

    def all_text(self) -> str:
        return "\n\n".join([*self.sections.values(), self.levels, self.summary])


def _source(state: dict, paths) -> str:
    texts = []
    for path in paths:
        value = state
        for key in path:
            value = (value or {}).get(key) if isinstance(value, dict) else None
        if value:
            texts.append(str(value))
    return "\n\n---\n\n".join(texts)


def _clean(text: str) -> str:
    text = re.sub(r"^```(?:markdown)?\s*|\s*```$", "", text.strip())
    return re.sub(r"^#\s+.*\n", "", text).strip()


def edit_section(llm: LLMCall, key: str, source: str, facts_text: str, feedback: list[str] | None = None) -> str:
    title = next(t for k, t, _p, _s in SECTIONS if k == key)
    extra = ""
    if key == "evidence":
        extra = ("\nThis source is a debate between a bullish and a bearish researcher. Rewrite it as two lists of "
                 "facts: '### Data pointing to strength' and '### Data pointing to weakness' (see section 4 of the "
                 "specification). Drop the arguments about what to do, and any conclusion about which side 'wins'.")
    fix = ""
    if feedback:
        fix = ("\n\nA quality-control review rejected the previous version for these problems. Fix every one:\n- "
               + "\n- ".join(feedback))
    user = (f"Section: {title}{extra}{fix}\n\nVERIFIED MARKET DATA (ground truth):\n{facts_text}\n\n"
            f"SOURCE TEXT TO REWRITE:\n{source}")
    return _clean(llm(editor_system(), user))


def write_summary(llm: LLMCall, sections: dict[str, str], facts_text: str, feedback: list[str] | None = None) -> tuple[str, str]:
    """(summary, levels) written only from already-factual sections."""
    fix = ("\n\nA quality-control review rejected the previous version for these problems. Fix every one:\n- "
           + "\n- ".join(feedback)) if feedback else ""
    user = ("Using ONLY the facts below, write two things.\n"
            "First, a market conditions summary: 4-6 sentences describing the current state of the market for this "
            "instrument (trend on each timeframe, momentum, flows/positioning, sentiment, notable data gaps). "
            "No advice, no forecasts, no ratings.\n"
            "Second, a Markdown table of the price levels the data highlights, with columns: Level | What it is | "
            "Why analysts watch it. Describe each level factually (e.g. '200-day simple moving average'), with no "
            "instructions.\n"
            "Output exactly in this format:\n=== SUMMARY ===\n<summary>\n=== LEVELS ===\n<table>" + fix +
            f"\n\nVERIFIED MARKET DATA:\n{facts_text}\n\nFACTUAL SECTIONS:\n" +
            "\n\n".join(f"## {k}\n{v}" for k, v in sections.items() if v))
    out = llm(editor_system(), user)
    summary, _, levels = out.partition("=== LEVELS ===")
    summary = summary.replace("=== SUMMARY ===", "").strip()
    return _clean(summary), _clean(levels)


def detect_gaps(state: dict) -> list[str]:
    gaps = []
    names = {"news_report": "News", "sentiment_report": "Sentiment", "fundamentals_report": "Fundamentals or on-chain data"}
    for key, label in names.items():
        text = state.get(key)
        if text is None:
            continue
        if not str(text).strip():
            gaps.append(f"{label}: no report was produced in this run.")
        elif _UNAVAILABLE.search(str(text)[:3000]):
            gaps.append(f"{label}: some of this data was unavailable when the report ran; that section notes what is missing.")
    return gaps


def edit_report(llm: LLMCall, state: dict, facts_text: str) -> EditedReport:
    report = EditedReport(gaps=detect_gaps(state))
    for key, _title, _part, paths in SECTIONS:
        source = _source(state, paths)
        if source.strip():
            report.sections[key] = edit_section(llm, key, source, facts_text)
    report.summary, report.levels = write_summary(llm, report.sections, facts_text)
    return report


def apply_fixes(llm: LLMCall, report: EditedReport, state: dict, facts_text: str,
                issues_by_section: dict[str, list[str]]) -> EditedReport:
    """Re-edit only the sections the quality-control agent flagged."""
    for key, issues in issues_by_section.items():
        if key in report.sections:
            paths = next(p for k, _t, _pt, p in SECTIONS if k == key)
            report.sections[key] = edit_section(llm, key, _source(state, paths), facts_text, issues)
    summary_issues = issues_by_section.get("summary", []) + issues_by_section.get("levels", [])
    if summary_issues or any(k in report.sections for k in issues_by_section):
        report.summary, report.levels = write_summary(llm, report.sections, facts_text, summary_issues or None)
    return report
