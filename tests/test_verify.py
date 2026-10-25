"""Second-source checks on extreme company figures."""

import pytest

from tradingagents.dataflows import verify
from tradingagents.dataflows.errors import VendorUnavailableError

# Micron-like: SEC's latest quarterly figure is fiscal Q3; Yahoo also has Q4.
_YAHOO = {
    "q_revenue": {"2026-09-03": 54.23e9, "2026-05-28": 41.46e9, "2025-08-28": 11.32e9, "2025-05-29": 9.30e9},
    "revenue": {"2026-09-03": 133.19e9}, "operating": {"2026-09-03": 99.34e9}, "net": {"2026-09-03": 84.97e9},
}


@pytest.mark.unit
def test_ordinary_figures_are_not_checked():
    called = []
    assert verify.check("X", {"revenue_growth_yoy": 0.2, "operating_margin": 0.3}, False,
                        fetch=lambda t: called.append(t)) == []
    assert called == []


@pytest.mark.unit
def test_extreme_growth_confirmed_and_newer_quarter_noted():
    metrics = {"revenue_growth_yoy": 3.457, "quarter_end": "2026-05-28"}
    notes = verify.check("MU", metrics, False, fetch=lambda t: _YAHOO)
    assert "CONFIRMED by Yahoo Finance (+345.8%)" in notes[0]
    assert "newer quarter (to 2026-09-03)" in notes[1] and "+379.1%" in notes[1]


@pytest.mark.unit
def test_historical_run_skips_newer_quarter():
    notes = verify.check("MU", {"revenue_growth_yoy": 3.457, "quarter_end": "2026-05-28"}, True,
                         fetch=lambda t: _YAHOO)
    assert len(notes) == 1


@pytest.mark.unit
def test_disagreement_is_flagged():
    notes = verify.check("MU", {"revenue_growth_yoy": 9.0, "quarter_end": "2026-05-28"}, True,
                         fetch=lambda t: _YAHOO)
    assert "DIFFERS" in notes[0]


@pytest.mark.unit
def test_margin_checked_against_same_fiscal_year():
    notes = verify.check("MU", {"operating_margin": 0.746, "fiscal_year_end": "2026-09-03"}, False,
                         fetch=lambda t: _YAHOO)
    assert "CONFIRMED by Yahoo Finance (74.6%)" in notes[0]


@pytest.mark.unit
def test_unreachable_second_source_says_so():
    def down(ticker):
        raise VendorUnavailableError("Yahoo down")

    notes = verify.check("MU", {"revenue_growth_yoy": 3.5, "quarter_end": "2026-05-28"}, False, fetch=down)
    assert "could not be cross-checked" in notes[0]
