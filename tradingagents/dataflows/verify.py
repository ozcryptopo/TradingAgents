"""Second-source checks for company figures that look extreme.

A number far outside the usual range (revenue tripling, a 75% operating margin)
is more often a data problem than news: a mis-tagged filing, a one-off, or a
mismatched period. Before such a figure reaches an analyst's report, it is
recomputed from an independent source (Yahoo Finance's income statements) for
the same period, and the report says whether the two agree.

On a live run it also notes a newer quarter that SEC's quarterly facts lack:
a company's fiscal fourth quarter is filed only inside its annual report, so
the latest *quarterly* SEC figure can be one quarter behind. Yahoo's statement
dates are period ends, not filing dates, so a historical run skips that note.
"""

from __future__ import annotations

import logging
from datetime import date

import yfinance as yf

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.vendors.yahoo.common import yf_retry

logger = logging.getLogger(__name__)

# (metric key, label, is it unusual?)
UNUSUAL = (
    ("revenue_growth_yoy", "revenue growth", lambda v: v > 1.5 or v < -0.5),
    ("operating_margin", "operating margin", lambda v: v > 0.6 or v < -0.3),
    ("net_margin", "net margin", lambda v: v > 0.5 or v < -0.3),
    ("liabilities_to_equity", "liabilities/equity", lambda v: v > 5),
)

_DAY_TOLERANCE = 10


def flagged(metrics: dict) -> list[tuple[str, str]]:
    """The (key, label) pairs of ``metrics`` outside their usual range."""
    return [(key, label) for key, label, odd in UNUSUAL if metrics.get(key) is not None and odd(metrics[key])]


def _series(frame, row: str) -> dict[str, float]:
    """{period end: value} for one income-statement row, or {}."""
    if frame is None or getattr(frame, "empty", True) or row not in frame.index:
        return {}
    out = {}
    for column, value in frame.loc[row].items():
        try:
            if value == value:  # skip NaN
                out[str(column)[:10]] = float(value)
        except (TypeError, ValueError):
            continue
    return out


def yahoo_statements(ticker: str) -> dict[str, dict[str, float]]:
    """Quarterly revenue and annual revenue / operating / net income from Yahoo."""
    quarterly = yf_retry(lambda: yf.Ticker(ticker).quarterly_income_stmt)
    annual = yf_retry(lambda: yf.Ticker(ticker).income_stmt)
    return {
        "q_revenue": _series(quarterly, "Total Revenue"),
        "revenue": _series(annual, "Total Revenue"),
        "operating": _series(annual, "Operating Income"),
        "net": _series(annual, "Net Income"),
    }


def _near(series: dict[str, float], when: str, offset_days: int = 0) -> tuple[str, float] | None:
    target = date.fromisoformat(when).toordinal() - offset_days
    best = min(series.items(), key=lambda kv: abs(date.fromisoformat(kv[0]).toordinal() - target), default=None)
    if best and abs(date.fromisoformat(best[0]).toordinal() - target) <= _DAY_TOLERANCE:
        return best
    return None


def _agrees(a: float, b: float) -> bool:
    return abs(a - b) <= 0.03 + 0.05 * abs(a)


def _yoy(series: dict[str, float], end: str) -> float | None:
    now, before = _near(series, end), _near(series, end, 365)
    if now and before and before[1]:
        return (now[1] - before[1]) / abs(before[1])
    return None


def check(ticker: str, metrics: dict, historical: bool, fetch=None) -> list[str]:
    """Plain-language verdicts on each unusual figure in ``metrics``."""
    odd = flagged(metrics)
    if not odd or not ticker:
        return []
    try:
        yahoo = (fetch or yahoo_statements)(ticker)
    except VendorUnavailableError as exc:
        return [f"{ticker}: unusual {', '.join(label for _, label in odd)} could not be cross-checked ({exc})."]

    notes = []
    for key, label in odd:
        value = metrics[key]
        if key == "revenue_growth_yoy":
            end = metrics.get("quarter_end")
            other = _yoy(yahoo["q_revenue"], end) if end else None
            if other is None:
                notes.append(f"{ticker}: {label} {value * 100:+.1f}% (quarter to {end}) could not be cross-checked; treat with caution.")
            elif _agrees(value, other):
                notes.append(f"{ticker}: {label} {value * 100:+.1f}% (quarter to {end}) CONFIRMED by Yahoo Finance ({other * 100:+.1f}%).")
            else:
                notes.append(f"{ticker}: {label} {value * 100:+.1f}% (quarter to {end}) DIFFERS from Yahoo Finance ({other * 100:+.1f}%); do not rely on it without checking the filing.")
            if not historical and end:
                newer = sorted(d for d in yahoo["q_revenue"] if d > end and date.fromisoformat(d).toordinal() - date.fromisoformat(end).toordinal() > _DAY_TOLERANCE)
                if newer:
                    growth = _yoy(yahoo["q_revenue"], newer[-1])
                    if growth is not None:
                        notes.append(
                            f"{ticker}: a newer quarter (to {newer[-1]}) shows revenue growth {growth * 100:+.1f}% "
                            f"(Yahoo Finance); SEC quarterly facts lag because a fiscal Q4 is filed only in the annual report."
                        )
            continue
        fy_end = metrics.get("fiscal_year_end")
        numerator = {"operating_margin": "operating", "net_margin": "net"}.get(key)
        if numerator and fy_end:
            revenue, part = _near(yahoo["revenue"], fy_end), _near(yahoo[numerator], fy_end)
            if revenue and part and revenue[1]:
                other = part[1] / revenue[1]
                verdict = "CONFIRMED by" if _agrees(value, other) else "DIFFERS from"
                notes.append(f"{ticker}: {label} {value * 100:.1f}% (fiscal year to {fy_end}) {verdict} Yahoo Finance ({other * 100:.1f}%).")
                continue
        notes.append(f"{ticker}: {label} {value:.2f} is unusual and could not be cross-checked; treat with caution.")
    return notes
