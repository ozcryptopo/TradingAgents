"""The PDF research report and the legal notices every report carries."""


import pytest

from tradingagents import report_pdf
from tradingagents.disclaimer import TOP_NOTICE
from tradingagents.reporting import _report_parts, write_report_tree

_DECISION = (
    "**Rating**: Underweight\n\n**Executive Summary**: Trim into strength.\n\n"
    "**Investment Thesis**: Momentum is negative.\n\n**Price Target**: 78500.0\n\n"
    "**Time Horizon**: 1-3 months"
)
_STATE = {"trade_date": "2026-10-25", "final_rating": "Underweight", "market_report": "## Tape\n\n| a | b |\n|---|---|\n| 1 | 2 |",
          "final_trade_decision": _DECISION}


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    _DECISION,
    "Rating: Underweight\n\nExecutive Summary: Trim into strength.\n\nInvestment Thesis: Momentum is negative.\n\n"
    "Price Target: 78500.0\n\nTime Horizon: 1-3 months",
])
def test_decision_fields_read_bold_and_plain_layouts(text):
    fields = report_pdf.decision_fields(text)
    assert fields["Rating"] == "Underweight"
    assert fields["Executive Summary"] == "Trim into strength."
    assert fields["Price Target"] == "78500.0"
    assert fields["Time Horizon"] == "1-3 months"


@pytest.mark.unit
def test_print_page_has_cover_notice_brand_and_disclosures(monkeypatch):
    monkeypatch.setenv("REPORT_BRAND", "Bright Launch Digital Research")
    monkeypatch.setenv("REPORT_PRIMARY_COLOR", "#0b1e3f")
    monkeypatch.setenv("REPORT_ACCENT_COLOR", "red; } body { display:none")   # rejected, default used
    page = report_pdf.render_pdf_html("BTC-USD", _STATE, None, _report_parts(_STATE))
    assert page.index('<div class="cover"') < page.index('<div class="notice"') < page.index('class="eyebrow">At a glance')
    assert "NOT INVESTMENT OR TRADING ADVICE." in page
    assert "Bright Launch Digital Research" in page and "78,500" in page and "1-3 months" in page
    assert "No advisory relationship" in page and "Bright Launch Digital Research is not a registered investment adviser" in page
    assert "--primary: #0b1e3f" in page and "display:none" not in page
    assert "http" not in page.split("<body>")[0].replace("http-equiv", "")   # nothing fetched


@pytest.mark.unit
def test_every_format_opens_with_the_notice(tmp_path, monkeypatch):
    monkeypatch.delenv("REPORT_BRAND", raising=False)
    write_report_tree(_STATE, "BTC-USD", tmp_path, html=True, pdf=False)
    md = (tmp_path / "complete_report.md").read_text()
    html = (tmp_path / "complete_report.html").read_text()
    assert md.splitlines()[2].startswith("> **NOT INVESTMENT OR TRADING ADVICE.**")
    assert "## Important disclosures" in md and "The publisher is not a registered investment adviser" in md
    assert html.index('class="notice"') < html.index("<h1")
    assert "Important disclosures" in html
    assert TOP_NOTICE.split(". ", 1)[1][:40] in html


@pytest.mark.unit
def test_missing_browser_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(report_pdf, "find_browser", lambda: None)
    write_report_tree(_STATE, "BTC-USD", tmp_path, html=False, pdf=True)
    assert not (tmp_path / "research_report.pdf").exists()
    assert "Chrome" in (tmp_path / "research_report_pdf_error.txt").read_text()


@pytest.mark.unit
@pytest.mark.skipif(not report_pdf.find_browser(), reason="no Chromium-based browser here")
def test_renders_a_real_pdf(tmp_path, monkeypatch):
    import socket
    monkeypatch.setattr(socket.socket, "connect", socket.socket.connect)  # the browser runs in its own process
    write_report_tree(_STATE, "BTC-USD", tmp_path, html=False, pdf=True)
    pdf = tmp_path / "research_report.pdf"
    assert pdf.exists() and pdf.read_bytes()[:4] == b"%PDF"
    assert not list(tmp_path.glob(".research_report_print.html"))
