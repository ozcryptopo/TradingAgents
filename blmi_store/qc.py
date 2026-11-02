"""The quality-control agent: nothing reaches a customer unless every check passes.

1. Advice scan (deterministic): no ratings, recommendations, targets, stops,
   sizing, hedges or instructions to the reader, in any wording we know of.
2. Number check (deterministic): every figure in the report must appear in the
   run's source data or the verified market data. Catches invented numbers.
3. Moving-average check (deterministic): the 50- and 200-day averages the report
   quotes must match the values computed from price data.
4. Reviewer (AI): reads the report against the verified data for factual errors,
   contradictions, mislabeled timing and any advice the patterns missed.

After the PDF is rendered, ``check_pdf`` scans its text again and confirms the
disclaimers are present.
"""

from __future__ import annotations

import bisect
import json
import re
from dataclasses import dataclass, field

from blmi_store.editor import EditedReport
from blmi_store.llm import LLMCall

# Each pattern is unambiguous advice in a market report. Words that also describe
# the market (buyers, sellers, sell-off, hedge funds, long-term) are deliberately
# not matched here; the AI reviewer judges those in context.
ADVICE_PATTERNS: list[tuple[str, str]] = [
    ("rating word", r"\b(?:overweight|underweight|outperform|underperform|accumulate)\b"),
    ("rating", r"\b(?:our|model|analyst|analysts'|consensus|investment|stock|AI|final|portfolio)\s+ratings?\b"
               r"|\bratings?\s*[:=]|\b(?:rated|rate[sd]?)\s+(?:as\s+)?(?:a\s+)?(?:buy|sell|hold)\b"),
    ("buy/sell call", r"\b(?:buy|sell)\b(?![- ]?(?:side|offs?\b))"),
    ("hold call", r"\bhold\s+(?:rating|call|recommendation|signal)\b|\b(?:a|the)\s+hold\b"),
    ("price target", r"\b(?:price|upside|downside)\s+targets?\b|\btarget\s+price\b|\btake[- ]profit\b"),
    ("stop", r"\bstop[- ]?loss(?:es)?\b|\bstops?\s+(?:at|below|above)\b|\btrailing\s+stop\b"),
    ("entry/exit", r"\b(?:entry|exit)\s+(?:points?|zones?|prices?|levels?|signals?)\b"),
    ("sizing", r"\bposition[- ]siz\w*|\bof\s+(?:the|your|a)\s+(?:current\s+)?(?:position|portfolio|sleeve)\b|\bsleeve\b"),
    ("exposure", r"\b(?:reduce|cut|add|increase|trim)\w*\s+(?:net\s+)?(?:exposure|position|holdings?)\b"),
    ("action verb", r"\b(?:re-?risk|de-?risk|trim the|go long|go short|enter (?:a )?(?:long|short)|initiate (?:new )?(?:longs?|shorts?)|naked shorts?)\b"),
    ("options strategy", r"\b(?:put|call)\s+spreads?\b|\bcovered\s+calls?\b|\bprotective\s+puts?\b|\bcollar\b"),
    ("hedging advice", r"\bhedg(?:e|es|ed|ing)\b(?!\s+funds?)"),
    ("recommendation", r"\brecommend\w*|\b(?:we|i)\s+(?:suggest|advise|believe you)\b|\badvis(?:e|able)\b"),
    ("reader instruction", r"\b(?:you|investors|traders|holders|buyers|readers)\s+(?:should|may want|might want|could consider|need to|must)\b"),
    ("consider", r"\bconsider(?:s|ed)?\s+(?:buying|selling|adding|trimming|reducing|shorting|taking|exiting|entering)\b"),
    ("ladder", r"\bladder(?:ed|ing)?\b"),
]
_ADVICE = [(label, re.compile(p, re.I)) for label, p in ADVICE_PATTERNS]

_DATE = re.compile(r"\b\d{4}[-‑]\d{2}[-‑]\d{2}\b|\b\d{1,2}[-‑/]\d{1,2}\b")
_NUM = re.compile(r"(?<![\w.])[-−+]?\$?(\d{1,3}(?:,\d{3})+|\d+)(\.\d+)?")


@dataclass
class QCResult:
    passed: bool
    issues: dict[str, list[str]] = field(default_factory=dict)   # section key -> problems
    reviewer: dict | None = None

    def add(self, section: str, problem: str) -> None:
        self.issues.setdefault(section, [])
        if problem not in self.issues[section]:
            self.issues[section].append(problem)

    def as_dict(self) -> dict:
        return {"passed": self.passed, "issues": self.issues, "reviewer": self.reviewer}


def advice_hits(text: str) -> list[tuple[str, str]]:
    hits = []
    for label, rx in _ADVICE:
        for m in rx.finditer(text or ""):
            start, end = max(0, m.start() - 50), min(len(text), m.end() + 50)
            hits.append((label, " ".join(text[start:end].split())))
    return hits


def _numbers(text: str) -> list[tuple[str, float, int]]:
    text = _DATE.sub(" ", (text or "").replace("‑", "-"))
    out = []
    for m in _NUM.finditer(text):
        whole, frac = m.group(1), m.group(2) or ""
        try:
            value = float(whole.replace(",", "") + frac)
        except ValueError:
            continue
        out.append((m.group(0), value, len(frac) - 1 if frac else 0))
    return out


def unsupported_numbers(text: str, source: str) -> list[str]:
    """Figures in ``text`` that no figure in ``source`` rounds to."""
    pool = sorted({abs(v) for _raw, v, _d in _numbers(source)})
    bad = []
    for raw, value, decimals in _numbers(text):
        v = abs(value)
        if decimals == 0 and v < 100:
            continue                      # counts, periods (14-day, 3 rounds), small integers
        if decimals == 0 and 1900 <= v <= 2100:
            continue                      # years
        tol = 0.5 * 10 ** (-decimals) + 1e-9
        i = bisect.bisect_left(pool, v - tol)
        if i < len(pool) and pool[i] <= v + tol:
            continue
        # also accept thousands/millions shorthand, e.g. 643.3 for 643,300,000 or 76.9 for 76,900
        if any(abs(v * k - s) <= tol * k for k in (1e3, 1e6, 1e9) for s in pool[bisect.bisect_left(pool, (v - tol) * k):
                                                                                     bisect.bisect_right(pool, (v + tol) * k)]):
            continue
        bad.append(raw.strip())
    return sorted(set(bad))


_MA = {
    "sma_200": re.compile(r"200[- ]?(?:day|d|period)?\s*(?:simple\s+)?(?:moving\s+average|SMA|MA|average)[^\d$\n]{0,40}\$?(\d[\d,]*\.?\d*)", re.I),
    "sma_50": re.compile(r"\b50[- ]?(?:day|d|period)?\s*(?:simple\s+)?(?:moving\s+average|SMA|MA|average)[^\d$\n]{0,40}\$?(\d[\d,]*\.?\d*)", re.I),
}


def moving_average_mismatches(text: str, facts: dict) -> list[str]:
    problems = []
    for key, rx in _MA.items():
        truth = facts.get(key)
        if not truth:
            continue
        for m in rx.finditer(text or ""):
            try:
                quoted = float(m.group(1).replace(",", ""))
            except ValueError:
                continue
            diff = abs(quoted - truth) / truth
            if 0.015 < diff < 0.2:        # far-off numbers are usually a different level, not this average
                label = "200-day" if key == "sma_200" else "50-day"
                problems.append(f"The {label} average is quoted as {m.group(1)} but the price data gives "
                                f"{truth:,.2f}. Use the verified value.")
    return problems


def reviewer_system() -> str:
    from blmi_store.editor import spec

    return (spec() + "\n\n---\n\nYOUR ROLE: you are the BLMI quality-control reviewer. Decide whether the REPORT "
            "below is safe to send to a paying customer, applying section 6 of the specification strictly: a single "
            "piece of advice, forecast, factual error or timing error fails it. Reply with the JSON object from "
            "section 6 only, with no other text.")


def _parse_json(text: str) -> dict | None:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def ai_review(llm: LLMCall, report: EditedReport, facts_text: str) -> dict:
    body = "\n\n".join(f"=== SECTION: {k} ===\n{v}" for k, v in
                       [*report.sections.items(), ("levels", report.levels), ("summary", report.summary)] if v)
    user = f"VERIFIED MARKET DATA:\n{facts_text}\n\nREPORT:\n{body}"
    for _ in range(2):
        parsed = _parse_json(llm(reviewer_system(), user))
        if parsed and parsed.get("verdict") in ("pass", "fail"):
            return parsed
    return {"verdict": "fail", "issues": [{"section": "summary", "type": "other", "quote": "",
                                           "fix": "The reviewer could not complete its check."}]}


def review(llm: LLMCall, report: EditedReport, state: dict, facts: dict, facts_text: str) -> QCResult:
    result = QCResult(passed=True)
    source = "\n".join(str(v) for v in _all_strings(state)) + "\n" + facts_text
    named = [*report.sections.items(), ("levels", report.levels), ("summary", report.summary)]
    for key, text in named:
        for label, snippet in advice_hits(text):
            result.add(key, f"Contains advice language ({label}): \"{snippet}\". Rewrite it as a neutral fact or remove it.")
        for raw in unsupported_numbers(text, source):
            result.add(key, f"The figure {raw} does not appear in the source data. Use the exact source figure or remove it.")
        for problem in moving_average_mismatches(text, facts):
            result.add(key, problem)
    if not report.sections.get("market"):
        result.add("market", "The price, trend and momentum section is missing.")
    deterministic_failed = bool(result.issues)
    # Only spend a reviewer call once the cheap checks pass; it would see the same problems otherwise.
    if not deterministic_failed:
        verdict = ai_review(llm, report, facts_text)
        result.reviewer = verdict
        for issue in verdict.get("issues") or []:
            key = issue.get("section") or "summary"
            if key not in dict(named):
                key = "summary"
            result.add(key, f"{issue.get('type', 'issue')}: \"{issue.get('quote', '')}\". {issue.get('fix', '')}".strip())
        if verdict.get("verdict") != "pass":
            result.add("summary", "The reviewer did not approve the report.") if not verdict.get("issues") else None
    result.passed = not result.issues
    return result


def _all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _all_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _all_strings(v)


REQUIRED_PDF_TEXT = ("FOR EDUCATIONAL PURPOSES ONLY", "NOT INVESTMENT ADVICE", "About this report",
                     "Important disclosures", "Facts only")


def check_pdf(pdf_path: str) -> list[str]:
    """Scan the rendered PDF: disclaimers present, no advice in the analysis pages."""
    import pymupdf

    from tradingagents.disclaimer import EDUCATIONAL_NOTICE

    doc = pymupdf.open(pdf_path)
    pages = [" ".join(p.get_text().split()) for p in doc]
    whole = " ".join(pages)
    problems = [f"The PDF is missing the required text \"{t}\"." for t in REQUIRED_PDF_TEXT
                if t.lower() not in whole.lower()]
    notice = " ".join(EDUCATIONAL_NOTICE.split())
    back = next((i for i, t in enumerate(pages) if "Methodology, data and disclosures" in t and i > 2), len(pages))
    for i, text in enumerate(pages):
        if i < 2 or i >= back:            # cover, About page and disclosures carry the legal wording
            continue
        text = text.replace(notice, " ")
        for label, snippet in advice_hits(text):
            problems.append(f"Page {i + 1} contains advice language ({label}): \"{snippet}\"")
    return problems
