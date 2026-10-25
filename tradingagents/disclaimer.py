"""The legal notices every report carries.

A short notice goes at the top of every report (PDF, HTML and Markdown) and the
full disclosures at the end. ``publisher()`` names whoever publishes the report
(REPORT_BRAND), falling back to a neutral phrase.

This text is a reasonable general-purpose starting point, not legal advice;
have a securities lawyer review it before publishing or selling reports.
"""

from tradingagents.branding import brand


def publisher() -> str:
    return brand() or "The publisher"


TOP_NOTICE = (
    "NOT INVESTMENT OR TRADING ADVICE. This report is AI-generated research for informational and "
    "educational purposes only. It is not a recommendation or offer to buy, sell or hold any security, "
    "digital asset or other instrument, and it does not consider your personal financial situation. "
    "Ratings, price targets and trade plans are model outputs, not instructions. Do your own research and "
    "consult a licensed financial professional before making any investment decision. See the full "
    "disclosures at the end of this report."
)


def full_disclosures() -> list[tuple[str, str]]:
    """(heading, text) pairs for the end of a report."""
    who = publisher()
    return [
        ("Not investment advice",
         "This report is provided for informational and educational purposes only. It does not constitute "
         "investment, financial, trading, legal, tax or accounting advice, and nothing in it is a "
         "recommendation, offer or solicitation to buy, sell or hold any security, digital asset, derivative "
         "or other financial instrument, or to adopt any investment strategy."),
        ("No advisory relationship",
         f"{who} is not a registered investment adviser, broker-dealer or financial planner. Reading or "
         "receiving this report does not create an advisory, fiduciary or client relationship. The report is "
         "general and impersonal: it is not tailored to any reader's objectives, financial situation, risk "
         "tolerance or needs."),
        ("AI-generated content",
         "This report was produced by artificial-intelligence models working from automated data sources. "
         "AI output can be inaccurate, incomplete, inconsistent or out of date, and can state wrong figures "
         "with confidence. Ratings, price targets, levels and trade plans are hypothetical model outputs, "
         "not predictions or guarantees."),
        ("Data and accuracy",
         "Data comes from third-party and public sources believed to be reliable but not verified "
         "independently in full. No representation or warranty, express or implied, is made as to its "
         "accuracy, completeness or timeliness. Information may change without notice and this report will "
         "not be updated."),
        ("Risk",
         "Investing and trading involve substantial risk, including the possible loss of all capital. Digital "
         "assets, leveraged products and derivatives are especially volatile. Past performance and historical "
         "patterns do not indicate future results. Forward-looking statements are uncertain and actual "
         "results may differ materially."),
        ("Conflicts of interest",
         f"{who}, its owners and affiliates may hold, buy or sell positions in the instruments discussed, "
         "before or after this report is published, and may act inconsistently with its conclusions."),
        ("No reliance; limitation of liability",
         "You are solely responsible for your own investment decisions. To the fullest extent permitted by "
         f"law, {who} and its owners, affiliates and providers accept no liability for any loss or damage, "
         "direct or indirect, arising from use of or reliance on this report. Consult a licensed financial "
         "professional before acting on any information here."),
        ("Distribution",
         "This report is not directed at any person in any jurisdiction where its publication or use would be "
         "unlawful. Do not redistribute it as personalised advice."),
    ]


def markdown_top() -> str:
    return f"> **{TOP_NOTICE.split('. ', 1)[0]}.** {TOP_NOTICE.split('. ', 1)[1]}\n\n"


def markdown_bottom() -> str:
    parts = ["## Important disclosures", ""]
    for heading, text in full_disclosures():
        parts += [f"**{heading}.** {text}", ""]
    return "\n".join(parts)
