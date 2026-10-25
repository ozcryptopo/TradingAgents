"""The name shown on reports and in the terminal.

Reports and screens carry no third-party branding. Set ``REPORT_BRAND`` (in
.env or the shell) to put your own name on them, e.g. ``REPORT_BRAND=Bright
Launch Research``; leave it unset for unbranded output.
"""

import os

DEFAULT_NAME = "Multi-Agent Market Research"


def brand() -> str:
    """The configured brand, or an empty string for none."""
    return os.getenv("REPORT_BRAND", "").strip()


def display_name() -> str:
    """What to call the tool on screen: the brand, else a neutral name."""
    return brand() or DEFAULT_NAME
