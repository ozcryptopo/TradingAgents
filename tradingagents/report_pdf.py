"""A designed, branded PDF research report for a completed run.

The page is laid out for print (a cover, an at-a-glance page with the call,
the full analysis, then methodology and disclosures, with running headers and
page numbers) and rendered to PDF by a Chromium-based browser in headless mode
(Chrome, Edge, Brave or Chromium), which every Mac with Chrome already has.

Branding comes from the environment (.env), all optional:
    REPORT_BRAND          name on the cover, headers and footers
    REPORT_PRIMARY_COLOR  main colour, e.g. #0b1e3f
    REPORT_ACCENT_COLOR   accent colour, e.g. #f4811e
    REPORT_HIGHLIGHT_COLOR  second accent, e.g. #ffd166
    REPORT_LOGO           path to a PNG, JPG or SVG logo for the cover
    REPORT_CONTACT        a website or contact line for the cover and disclosures
    REPORT_PDF_BROWSER    path to the browser, if it is not found automatically
"""

from __future__ import annotations

import base64
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from html import escape
from pathlib import Path

from tradingagents.agents.rating import run_rating
from tradingagents.branding import brand
from tradingagents.disclaimer import TOP_NOTICE, full_disclosures
from tradingagents.report_html import _CATEGORY, _markdown, _render_agent_text
from tradingagents.reporting import analyst_names

logger = logging.getLogger(__name__)

RENDER_TIMEOUT_SECONDS = 120
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
_TONE = {"Buy": "#0f8a5f", "Overweight": "#0f8a5f", "Hold": "#6b7280", "Underweight": "#c2410c", "Sell": "#b91c1c"}
_LOGO_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml"}

_MAC_BROWSERS = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
)
_PATH_BROWSERS = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "msedge", "chrome")


def _color(name: str, default: str) -> str:
    value = os.getenv(name, "").strip()
    return value if _HEX.match(value) else default


def _logo_tag() -> str:
    path = os.getenv("REPORT_LOGO", "").strip()
    if not path:
        return ""
    file = Path(path).expanduser()
    kind = _LOGO_TYPES.get(file.suffix.lower())
    if not kind or not file.is_file() or file.stat().st_size > 2_000_000:
        logger.warning("REPORT_LOGO %s is not a PNG/JPG/SVG under 2 MB; leaving it off", path)
        return ""
    data = base64.b64encode(file.read_bytes()).decode()
    return f'<img class="logo" src="data:{kind};base64,{data}" alt="">'


def decision_fields(text: str) -> dict[str, str]:
    """Rating, summary, thesis, target and horizon from the Portfolio Manager's text."""
    fields = {}
    labels = ("Rating", "Executive Summary", "Investment Thesis", "Price Target", "Time Horizon")
    pattern = re.compile(
        r"^\s*\**\s*(" + "|".join(labels) + r")\s*\**\s*:\s*\**\s*(.*?)(?=^\s*\**\s*(?:"
        + "|".join(labels) + r")\s*\**\s*:|\Z)",
        re.S | re.M,
    )
    for label, value in pattern.findall(text or ""):
        fields.setdefault(label, value.strip())
    return fields


def _clean_target(value: str) -> str:
    if not value or value.lower().startswith("not provided"):
        return "Not provided"
    try:
        number = float(value.replace(",", "").replace("$", "").split()[0])
        return f"{number:,.2f}" if number < 1000 else f"{number:,.0f}"
    except (ValueError, IndexError):
        return value[:40]


def _css(primary: str, accent: str, highlight: str, name: str, ticker: str) -> str:
    running = escape(f"{name + ' · ' if name else ''}{ticker} Research Report").replace('"', "'")
    return f"""
@page {{
  size: Letter; margin: 0.85in 0.8in 0.85in 0.8in;
  @top-left {{ content: "{running}"; font: 600 8pt -apple-system, Helvetica, Arial, sans-serif; color: #6b7280; }}
  @top-right {{ content: "AI-generated research · Not investment advice"; font: 8pt -apple-system, Helvetica, Arial, sans-serif; color: #9ca3af; }}
  @bottom-right {{ content: "Page " counter(page) " of " counter(pages); font: 8pt -apple-system, Helvetica, Arial, sans-serif; color: #6b7280; }}
}}
@page cover {{ margin: 0; @top-left {{ content: none; }} @top-right {{ content: none; }} @bottom-right {{ content: none; }} }}
:root {{ --primary: {primary}; --accent: {accent}; --highlight: {highlight};
  --ink: #111827; --muted: #6b7280; --rule: #e5e7eb; --wash: #f6f7f9;
  --display: 'Space Grotesk', 'Avenir Next', 'Helvetica Neue', 'Segoe UI', Arial, sans-serif;
  --text: 'Inter', -apple-system, 'Helvetica Neue', 'Segoe UI', Arial, sans-serif;
  --mono: 'IBM Plex Mono', 'SF Mono', Menlo, Consolas, monospace; }}
* {{ box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
html, body {{ margin: 0; padding: 0; }}
body {{ font: 10pt/1.55 var(--text); color: var(--ink); }}
h1, h2, h3, h4 {{ font-family: var(--display); }}

/* Cover */
.cover {{ page: cover; break-after: page; width: 8.5in; height: 11in; position: relative;
  background: var(--primary); color: #fff; padding: 0.9in 0.85in; overflow: hidden; }}
.cover::before, .cover::after {{ content: ""; position: absolute; border-radius: 50%; }}
.cover::after {{ right: -1.7in; top: -1.7in; width: 4.6in; height: 4.6in; border: 0.05in solid var(--accent); }}
.cover::before {{ right: -1.15in; top: -1.15in; width: 3.5in; height: 3.5in; border: 0.03in solid var(--highlight); }}
.cover .band {{ position: absolute; left: 0; bottom: 0; width: 100%; height: 0.22in;
  background: linear-gradient(90deg, var(--accent), var(--highlight)); }}
.cover .logo {{ max-height: 0.7in; max-width: 2.6in; margin-bottom: 0.25in; }}
.cover .brand {{ font: 700 11pt var(--display); letter-spacing: 0.14em;
  text-transform: uppercase; color: var(--highlight); }}
.cover .kind {{ margin-top: 2.1in; font: 600 10pt var(--text); letter-spacing: 0.18em;
  text-transform: uppercase; color: rgba(255,255,255,0.7); }}
.cover h1 {{ margin: 0.12in 0 0; font-size: 60pt; line-height: 1; letter-spacing: -0.02em; }}
.cover .sub {{ margin-top: 0.14in; font-size: 13pt; color: rgba(255,255,255,0.85); }}
.tiles {{ display: flex; gap: 0.18in; margin-top: 0.7in; }}
.tile {{ flex: 1; padding: 0.16in 0.18in; border-radius: 8px; background: rgba(255,255,255,0.08);
  border: 1px solid rgba(255,255,255,0.16); }}
.tile .label {{ font: 600 7.5pt var(--text); letter-spacing: 0.12em; text-transform: uppercase;
  color: rgba(255,255,255,0.65); }}
.tile .value {{ margin-top: 0.05in; font: 700 17pt var(--display); }}
.tile .value.rating {{ display: inline-block; padding: 0.02in 0.12in; border-radius: 4px; background: var(--tone); color: #fff; }}
.cover-notice {{ position: absolute; left: 0.85in; right: 0.85in; bottom: 1.0in; padding: 0.12in 0.16in;
  border: 1px solid rgba(255,255,255,0.25); border-radius: 6px; font-size: 7.5pt; line-height: 1.45;
  color: rgba(255,255,255,0.85); background: rgba(0,0,0,0.18); }}
.cover-notice strong {{ color: var(--highlight); }}
.notice {{ margin: 0 0 0.22in; padding: 0.1in 0.14in; border: 1px solid #fca5a5; border-left: 4px solid #b91c1c;
  border-radius: 4px; background: #fef2f2; font-size: 7.8pt; line-height: 1.45; color: #374151; }}
.notice strong {{ color: #991b1b; }}
.cover .foot {{ position: absolute; left: 0.85in; right: 0.85in; bottom: 0.55in;
  font-size: 8pt; color: rgba(255,255,255,0.65); display: flex; justify-content: space-between; }}

/* At a glance */
.glance {{ break-after: page; }}
.eyebrow {{ font: 700 8pt var(--text); letter-spacing: 0.16em; text-transform: uppercase; color: var(--accent); }}
.glance h2 {{ margin: 0.04in 0 0.18in; font-size: 22pt; color: var(--primary); }}
.facts {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0; border: 1px solid var(--rule);
  border-radius: 8px; overflow: hidden; margin-bottom: 0.25in; }}
.facts div {{ padding: 0.12in 0.14in; border-right: 1px solid var(--rule); background: var(--wash); }}
.facts div:last-child {{ border-right: 0; }}
.facts .label {{ font: 600 7pt var(--text); letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); }}
.facts .value {{ margin-top: 0.03in; font: 700 13pt var(--display); color: var(--primary); }}
.facts .value.rating {{ color: var(--tone); }}
.callout {{ border-left: 4px solid var(--accent); background: var(--wash); padding: 0.14in 0.18in;
  border-radius: 0 6px 6px 0; margin: 0 0 0.2in; }}
.callout h3 {{ margin: 0 0 0.06in; font-size: 11pt; color: var(--primary); }}
.callout p {{ margin: 0; }}
.toc {{ margin-top: 0.25in; }}
.toc h3 {{ font-size: 11pt; color: var(--primary); margin: 0 0 0.08in; }}
.toc ol {{ margin: 0; padding-left: 0.2in; columns: 2; column-gap: 0.4in; font-size: 9pt; }}
.toc li {{ margin: 0.03in 0; break-inside: avoid; }}
.toc li span {{ color: var(--muted); }}

/* Body */
section.part {{ break-before: page; }}
section.part > h2 {{ margin: 0 0 0.2in; padding-bottom: 0.08in; font-size: 18pt; color: var(--primary);
  border-bottom: 3px solid var(--accent); }}
h3.agent {{ margin: 0.3in 0 0.1in; font-size: 12.5pt; color: var(--primary);
  display: flex; align-items: center; gap: 0.08in; break-after: avoid; }}
h3.agent::before {{ content: ""; width: 0.09in; height: 0.09in; border-radius: 2px; background: var(--accent); }}
section.part > h2 + h3.agent {{ margin-top: 0; }}
.prose h4, .prose h5, .prose h6 {{ margin: 0.18in 0 0.06in; font-size: 10.5pt; color: var(--primary); break-after: avoid; }}
.prose p, .prose ul, .prose ol {{ margin: 0 0 0.09in; }}
.prose li {{ margin: 0.02in 0; }}
.prose strong {{ color: #000; }}
.prose blockquote {{ margin: 0.1in 0; padding: 0.04in 0.14in; border-left: 3px solid var(--rule); color: var(--muted); }}
.prose code {{ font: 8.5pt var(--mono); background: var(--wash); padding: 0 0.03in; border-radius: 3px; }}
.prose pre {{ background: var(--wash); padding: 0.1in; border-radius: 6px; white-space: pre-wrap; font-size: 8pt; }}
.prose hr {{ border: 0; border-top: 1px solid var(--rule); margin: 0.16in 0; }}
.table {{ margin: 0.08in 0 0.14in; }}
table {{ width: 100%; border-collapse: collapse; font-size: 8.5pt; font-variant-numeric: tabular-nums; break-inside: auto; }}
thead {{ display: table-header-group; }}
tr {{ break-inside: avoid; }}
th {{ background: var(--primary); color: #fff; font-weight: 600; text-align: left; padding: 0.05in 0.07in; }}
td {{ padding: 0.045in 0.07in; border-bottom: 1px solid var(--rule); vertical-align: top; }}
tbody tr:nth-child(even) td {{ background: var(--wash); }}

/* Back matter */
.back {{ break-before: page; }}
.back h2 {{ font-size: 16pt; color: var(--primary); margin: 0 0 0.12in; border-bottom: 3px solid var(--accent); padding-bottom: 0.06in; }}
.back h3 {{ font-size: 11pt; color: var(--primary); margin: 0.22in 0 0.06in; }}
.back dl {{ display: grid; grid-template-columns: 1.6in 1fr; gap: 0.05in 0.2in; margin: 0; font-size: 9pt; }}
.back dt {{ color: var(--muted); }}
.back dd {{ margin: 0; }}
.back p, .back li {{ font-size: 8.5pt; color: #374151; }}
"""


def _vendor_text(chain: str) -> str:
    return " → ".join(v.strip() for v in str(chain).split(",") if v.strip())


def render_pdf_html(ticker: str, final_state: dict, settings: dict | None, parts) -> str:
    """The print-designed report page that is rendered to PDF."""
    md = _markdown()
    name = brand()
    primary = _color("REPORT_PRIMARY_COLOR", "#0b1e3f")
    accent = _color("REPORT_ACCENT_COLOR", "#f4811e")
    highlight = _color("REPORT_HIGHLIGHT_COLOR", "#ffd166")
    contact = escape(os.getenv("REPORT_CONTACT", "").strip())

    decision = final_state.get("final_trade_decision", "") or ""
    fields = decision_fields(decision)
    rating = run_rating(final_state) if decision else ""
    tone = _TONE.get(rating, "#6b7280")
    target = _clean_target(fields.get("Price Target", ""))
    horizon = fields.get("Time Horizon", "") or "Not provided"
    if horizon.lower().startswith("not provided"):
        horizon = "Not provided"
    date = final_state.get("trade_date", "") or ""
    asset = "Crypto asset" if final_state.get("asset_type") == "crypto" else "Equity"
    generated = datetime.now().strftime("%B %-d, %Y" if sys.platform != "win32" else "%B %d, %Y")
    head, rest = TOP_NOTICE.split(". ", 1)
    notice = f"<strong>{escape(head)}.</strong> {escape(rest)}"
    summary = fields.get("Executive Summary", "")
    thesis = fields.get("Investment Thesis", "")

    cover = f"""
<div class="cover" style="--tone:{tone}">
  {_logo_tag()}
  {f'<div class="brand">{escape(name)}</div>' if name else ''}
  <div class="kind">{escape(asset)} Research Report</div>
  <h1>{escape(ticker)}</h1>
  <div class="sub">Multi-agent analysis as of {escape(date)}</div>
  <div class="tiles">
    <div class="tile"><div class="label">Rating</div><div class="value rating">{escape(rating or 'Review')}</div></div>
    <div class="tile"><div class="label">Price target</div><div class="value">{escape(target)}</div></div>
    <div class="tile"><div class="label">Time horizon</div><div class="value" style="font-size:11pt;line-height:1.3">{escape(horizon[:90])}</div></div>
  </div>
  <div class="cover-notice">{notice}</div>
  <div class="foot"><span>Prepared {escape(generated)}{f' · {contact}' if contact else ''}</span><span>AI-generated research · Not investment advice</span></div>
  <div class="band"></div>
</div>"""

    toc_items = []
    for heading, _folder, written in parts:
        label = heading.partition(". ")[2] or heading
        agents = ", ".join(agent for agent, _f, _t in written)
        toc_items.append(f"<li>{escape(label)} <span>— {escape(agents)}</span></li>")

    glance = f"""
<section class="glance" style="--tone:{tone}">
  <div class="notice">{notice}</div>
  <div class="eyebrow">At a glance</div>
  <h2>{escape(ticker)}: {escape(rating or 'Under review')}</h2>
  <div class="facts">
    <div><div class="label">Rating</div><div class="value rating">{escape(rating or 'Review')}</div></div>
    <div><div class="label">Price target</div><div class="value">{escape(target)}</div></div>
    <div><div class="label">Horizon</div><div class="value" style="font-size:9pt;line-height:1.3">{escape(horizon[:90])}</div></div>
    <div><div class="label">Analysis date</div><div class="value">{escape(date)}</div></div>
  </div>
  {f'<div class="callout"><h3>Executive summary</h3><div class="prose">{md.render(summary)}</div></div>' if summary else ''}
  {f'<div class="callout"><h3>Investment thesis</h3><div class="prose">{md.render(thesis)}</div></div>' if thesis else ''}
  <div class="toc"><h3>Inside this report</h3><ol>{"".join(toc_items)}<li>Methodology, data and disclosures</li></ol></div>
</section>"""

    body = []
    for heading, _folder, written in parts:
        body.append(f'<section class="part"><h2>{escape(heading.partition(". ")[2] or heading)}</h2>')
        for agent, _filename, text in written:
            body.append(f'<h3 class="agent">{escape(agent)}</h3><div class="prose">{_render_agent_text(md, text)}</div>')
        body.append("</section>")

    method = []
    if settings:
        s = settings.get
        for tier in ("deep", "quick"):
            provider = s(f"{tier}_think_provider") or s("llm_provider", "?")
            method.append((f"{tier.capitalize()}-thinking model", f"{provider} · {s(f'{tier}_think_llm', '?')}"))
        method.append(("Analysts", ", ".join(analyst_names(s("analysts")))))
        method.append(("Debate rounds", f"research {s('max_debate_rounds', '?')}, risk {s('max_risk_discuss_rounds', '?')}"))
        vendors = {**(s("data_vendors") or {}), **(s("tool_vendors") or {})}
        for key, chain in vendors.items():
            method.append((f"Data: {_CATEGORY.get(key, key)}", _vendor_text(chain)))
    method_rows = "".join(f"<dt>{escape(k)}</dt><dd>{escape(str(v))}</dd>" for k, v in method)
    disclosures = "".join(f"<p><strong>{escape(h)}.</strong> {escape(t)}</p>" for h, t in full_disclosures())
    back = f"""
<section class="back">
  <h2>Methodology, data and disclosures</h2>
  <h3>How this report was produced</h3>
  <p>A team of AI agents produced this report. Four analysts (market, sentiment, news and fundamentals) gathered
  data; a bull and a bear researcher debated it; a research manager judged the debate; a trader proposed a plan;
  aggressive, neutral and conservative risk analysts challenged it; and a portfolio manager made the final call.
  Data is limited to what was published by the analysis date. Unusual company figures are cross-checked against a
  second source where possible, and the report states the result.</p>
  {f'<dl>{method_rows}</dl>' if method_rows else ''}
  <h3>Important disclosures</h3>
  {disclosures}
  <p>Generated {escape(generated)}{f' · {contact}' if contact else ''}.</p>
</section>"""

    title = escape(f"{ticker} {date} {rating}".strip())
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>{title} research report</title>
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<style>{_css(primary, accent, highlight, name, ticker)}</style>
</head><body>
{cover}
{glance}
{"".join(body)}
{back}
</body></html>
"""


def find_browser() -> str | None:
    """A Chromium-based browser that can print to PDF, or None."""
    configured = os.getenv("REPORT_PDF_BROWSER", "").strip()
    if configured and Path(configured).exists():
        return configured
    for path in _MAC_BROWSERS:
        if Path(path).exists():
            return path
    for name in _PATH_BROWSERS:
        found = shutil.which(name)
        if found:
            return found
    for root in (os.getenv("PLAYWRIGHT_BROWSERS_PATH", ""), "/opt/pw-browsers"):
        candidate = Path(root) / "chromium" if root else None
        if candidate and candidate.exists():
            return str(candidate)
    return None


def html_to_pdf(html_file: Path, pdf_file: Path, browser: str | None = None) -> tuple[bool, str]:
    """Print ``html_file`` to ``pdf_file`` with a headless browser; (ok, message)."""
    browser = browser or find_browser()
    if not browser:
        return False, ("No Chrome, Edge, Brave or Chromium found to make the PDF. Install Google Chrome, or set "
                       "REPORT_PDF_BROWSER to a Chromium-based browser.")
    # Headless Chrome uses a throwaway profile of its own, so a running Chrome
    # window is untouched. Some builds keep running after writing the file, so
    # the PDF is watched for and the browser stopped once it is complete.
    command = [
        browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--hide-scrollbars", "--no-pdf-header-footer", f"--print-to-pdf={pdf_file}", html_file.resolve().as_uri(),
    ]
    if sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0:
        command.insert(1, "--no-sandbox")
    pdf_file.unlink(missing_ok=True)
    try:
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    except OSError as exc:
        return False, f"The browser could not be started ({exc})."
    deadline = time.monotonic() + RENDER_TIMEOUT_SECONDS
    last_size = -1
    while time.monotonic() < deadline:
        if process.poll() is not None:
            break
        size = pdf_file.stat().st_size if pdf_file.exists() else -1
        if size > 1000 and size == last_size:
            break   # written and no longer growing
        last_size = size
        time.sleep(0.5)
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
    stderr = process.stderr.read() if process.stderr else ""
    if pdf_file.exists() and pdf_file.stat().st_size > 1000:
        return True, str(pdf_file)
    detail = stderr.strip().splitlines()[-1:] or [""]
    return False, f"The browser did not produce a PDF. {detail[0][:200]}"


def write_pdf(ticker: str, final_state: dict, settings: dict | None, parts, save_path: Path) -> tuple[bool, str]:
    """Render the report and write ``research_report.pdf`` into ``save_path``."""
    save_path = Path(save_path)
    page = save_path / ".research_report_print.html"
    page.write_text(render_pdf_html(ticker, final_state, settings, parts), encoding="utf-8")
    try:
        return html_to_pdf(page, save_path / "research_report.pdf")
    finally:
        page.unlink(missing_ok=True)
