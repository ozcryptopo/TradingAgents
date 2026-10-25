"""CFTC Commitments of Traders vendor: weekly futures positioning (no key).

Who holds what in the major financial futures, from the U.S. regulator's
Traders in Financial Futures (TFF) report: leveraged funds (hedge funds, CTAs),
asset managers (pensions, mutual funds) and dealers (banks), long and short,
for equity-index, Treasury, volatility, dollar and crypto futures.

Uses the CFTC's public Socrata API (https://publicreporting.cftc.gov), no key.
Positions are as of each Tuesday and published the following Friday.

Point in time: a report is used only once it would have been published (its
Tuesday plus three days) on or before the analysis date.
"""

import logging
from datetime import datetime, timedelta

import requests

from tradingagents.dataflows.errors import VendorUnavailableError
from tradingagents.dataflows.symbols import crypto_base

logger = logging.getLogger(__name__)

TFF_URL = "https://publicreporting.cftc.gov/resource/gpe5-46if.json"
REQUEST_TIMEOUT = 30
DEFAULT_WEEKS = 8
PUBLICATION_LAG_DAYS = 3  # Tuesday positions, Friday release

# Market alias -> (CFTC contract market code, label).
MARKETS = {
    "sp500": ("13874A", "E-mini S&P 500"),
    "nasdaq100": ("209742", "E-mini Nasdaq-100"),
    "russell2000": ("239742", "E-mini Russell 2000"),
    "dow": ("124603", "E-mini Dow ($5)"),
    "vix": ("1170E1", "VIX futures"),
    "treasury_2y": ("042601", "2-year Treasury note"),
    "treasury_5y": ("044601", "5-year Treasury note"),
    "treasury_10y": ("043602", "10-year Treasury note"),
    "treasury_30y": ("020601", "30-year Treasury bond"),
    "ultra_bond": ("020604", "Ultra Treasury bond"),
    "dollar": ("098662", "U.S. Dollar Index"),
    "bitcoin": ("133741", "CME Bitcoin"),
    "ether": ("146021", "CME Ether"),
}

ALIASES = {
    "spx": "sp500", "s&p500": "sp500", "s&p_500": "sp500", "es": "sp500", "spy": "sp500",
    "nasdaq": "nasdaq100", "ndx": "nasdaq100", "qqq": "nasdaq100", "nq": "nasdaq100",
    "russell": "russell2000", "iwm": "russell2000",
    "10y": "treasury_10y", "10y_treasury": "treasury_10y", "tlt": "treasury_30y",
    "30y": "treasury_30y", "2y": "treasury_2y", "5y": "treasury_5y", "bonds": "treasury_10y",
    "dxy": "dollar", "usd": "dollar", "btc": "bitcoin", "eth": "ether", "ethereum": "ether",
}

# (label, long field candidates, short field candidates). TFF uses no "_all"
# suffix for asset managers and leveraged funds but does for dealers; both
# spellings are tried so a schema tweak does not blank the report.
GROUPS = (
    ("Leveraged funds (hedge funds/CTAs)", ("lev_money_positions_long", "lev_money_positions_long_all"),
     ("lev_money_positions_short", "lev_money_positions_short_all")),
    ("Asset managers", ("asset_mgr_positions_long", "asset_mgr_positions_long_all"),
     ("asset_mgr_positions_short", "asset_mgr_positions_short_all")),
    ("Dealers (banks)", ("dealer_positions_long_all", "dealer_positions_long"),
     ("dealer_positions_short_all", "dealer_positions_short")),
)


def resolve_market(market: str | None, symbol: str = "") -> str | None:
    """A market alias from the model's argument, else one suited to the instrument."""
    key = (market or "").strip().lower().replace(" ", "_").replace("-", "_")
    if key and key != "auto":
        key = ALIASES.get(key, key)
        return key if key in MARKETS else None
    base = crypto_base(symbol)
    if base == "BTC":
        return "bitcoin"
    if base == "ETH":
        return "ether"
    return "sp500"


def _request(code: str, start: str, end: str) -> list:
    params = {
        "$where": (
            f"cftc_contract_market_code='{code}' AND report_date_as_yyyy_mm_dd >= '{start}' "
            f"AND report_date_as_yyyy_mm_dd <= '{end}'"
        ),
        "$order": "report_date_as_yyyy_mm_dd ASC",
        "$limit": 100,
    }
    try:
        response = requests.get(TFF_URL, params=params, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as exc:
        raise VendorUnavailableError(f"CFTC unreachable: {exc}") from None
    if response.status_code == 429 or response.status_code >= 500:
        raise VendorUnavailableError(f"CFTC returned {response.status_code}")
    response.raise_for_status()
    return response.json()


def _field(row: dict, candidates) -> float | None:
    for name in candidates:
        if row.get(name) not in (None, ""):
            try:
                return float(row[name])
            except (TypeError, ValueError):
                return None
    return None


def get_futures_positioning(market: str | None, as_of_date: str, symbol: str = "", weeks: int | None = None) -> str:
    """Weekly futures positioning by trader group, as markdown."""
    alias = resolve_market(market, symbol)
    if alias is None:
        return (
            f"Unknown futures market '{market}'. Use one of: {', '.join(MARKETS)}."
        )
    code, label = MARKETS[alias]
    weeks = weeks or DEFAULT_WEEKS
    # Latest report that would have been published by the analysis date.
    end = datetime.strptime(as_of_date, "%Y-%m-%d") - timedelta(days=PUBLICATION_LAG_DAYS)
    start = end - timedelta(weeks=weeks + 1)
    rows = _request(code, start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))
    rows = sorted(rows, key=lambda r: r.get("report_date_as_yyyy_mm_dd", ""))[-weeks:]

    header = (
        f"## Futures positioning: {label} (CFTC Commitments of Traders, TFF)\n"
        f"- Weekly; positions as of each Tuesday, published the following Friday.\n"
    )
    if not rows:
        return header + (
            f"\nNO_DATA_AVAILABLE: no CFTC reports for {label} (code {code}) published by {as_of_date}. "
            f"Do not estimate positioning."
        )

    def nets(row):
        out = []
        for _, longs, shorts in GROUPS:
            long_, short = _field(row, longs), _field(row, shorts)
            out.append(None if long_ is None or short is None else long_ - short)
        return out

    latest, previous = rows[-1], rows[-2] if len(rows) > 1 else None
    open_interest = _field(latest, ("open_interest_all",))
    lines = [
        header,
        f"Latest report: {latest.get('report_date_as_yyyy_mm_dd', '')[:10]}. "
        f"Open interest: {open_interest:,.0f} contracts." if open_interest else
        f"Latest report: {latest.get('report_date_as_yyyy_mm_dd', '')[:10]}.",
        "",
        "| Group | Net position (long - short) | % of open interest | Change vs prior week |",
        "| --- | --- | --- | --- |",
    ]
    latest_nets = nets(latest)
    prior_nets = nets(previous) if previous else [None] * len(GROUPS)
    for (name, _, _), net, prior in zip(GROUPS, latest_nets, prior_nets, strict=True):
        if net is None:
            lines.append(f"| {name} | n/a | n/a | n/a |")
            continue
        pct = f"{net / open_interest * 100:+.1f}%" if open_interest else "n/a"
        change = f"{net - prior:+,.0f}" if prior is not None else "n/a"
        lines.append(f"| {name} | {net:+,.0f} | {pct} | {change} |")

    lines += [
        "",
        "Reading: leveraged funds are the fast, speculative money (extreme net shorts can fuel squeezes; "
        "extreme longs are crowded); asset managers are slower, longer-term holders; dealers are mostly "
        "the other side of client trades.",
        "",
        "| Week | " + " | ".join(name.split(" (")[0] + " net" for name, _, _ in GROUPS) + " |",
        "| --- |" + " --- |" * len(GROUPS),
    ]
    for row in rows:
        values = ["n/a" if v is None else f"{v:+,.0f}" for v in nets(row)]
        lines.append(f"| {row.get('report_date_as_yyyy_mm_dd', '')[:10]} | " + " | ".join(values) + " |")
    return "\n".join(lines) + "\n"
