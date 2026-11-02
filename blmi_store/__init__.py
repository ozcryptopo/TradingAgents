"""BLMI report store: sell facts-only market conditions reports on demand.

Two processes share this package:

- ``blmi_store.web``: the storefront, Stripe checkout and webhook, order status
  pages, downloads and a small admin page (FastAPI).
- ``blmi_store.worker``: takes paid orders off the queue, runs TradingAgents,
  has an editing agent rewrite the result as facts only, has a quality-control
  agent check it, renders the branded PDF and emails it to the buyer.
"""
