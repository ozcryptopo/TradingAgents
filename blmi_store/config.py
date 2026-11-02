"""Settings, all from environment variables (Railway service variables or .env)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

STATIC_DIR = Path(__file__).parent / "static"


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


@dataclass(frozen=True)
class Tier:
    key: str
    name: str
    price_cents: int
    analysts: tuple[str, ...]
    debate_rounds: int
    eta: str
    blurb: str


@dataclass
class Settings:
    base_url: str = field(default_factory=lambda: os.getenv("BASE_URL", "http://localhost:8000").rstrip("/"))
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", "sqlite:///blmi_store.db"))
    stripe_secret_key: str = field(default_factory=lambda: os.getenv("STRIPE_SECRET_KEY", ""))
    stripe_webhook_secret: str = field(default_factory=lambda: os.getenv("STRIPE_WEBHOOK_SECRET", ""))
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", "").rstrip("/"))
    supabase_service_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
    supabase_bucket: str = field(default_factory=lambda: os.getenv("SUPABASE_BUCKET", "reports"))
    local_storage_dir: str = field(default_factory=lambda: os.getenv("LOCAL_STORAGE_DIR", "./report-files"))
    resend_api_key: str = field(default_factory=lambda: os.getenv("RESEND_API_KEY", ""))
    email_from: str = field(default_factory=lambda: os.getenv(
        "EMAIL_FROM", "BrightLaunch Market Intelligence <reports@brightlaunchdigital.com>"))
    admin_email: str = field(default_factory=lambda: os.getenv("ADMIN_EMAIL", ""))
    admin_key: str = field(default_factory=lambda: os.getenv("ADMIN_KEY", ""))
    work_dir: str = field(default_factory=lambda: os.getenv("REPORT_WORK_DIR", "/tmp/blmi-reports"))
    max_attempts: int = field(default_factory=lambda: _int("MAX_RUN_ATTEMPTS", 2))
    qc_fix_rounds: int = field(default_factory=lambda: _int("QC_FIX_ROUNDS", 2))
    poll_seconds: int = field(default_factory=lambda: _int("WORKER_POLL_SECONDS", 10))
    brand: str = field(default_factory=lambda: os.getenv("REPORT_BRAND", "BrightLaunch Market Intelligence"))
    contact: str = field(default_factory=lambda: os.getenv("REPORT_CONTACT", "brightlaunchdigital.com"))

    @property
    def tiers(self) -> dict[str, Tier]:
        return {
            "quick": Tier("quick", "Quick report", _int("PRICE_QUICK_CENTS", 900),
                          ("market", "news", "fundamentals"), _int("QUICK_DEBATE_ROUNDS", 1),
                          "about 10-20 minutes",
                          "Trend, momentum, key levels, news and fundamentals or on-chain data."),
            "deep": Tier("deep", "Deep report", _int("PRICE_DEEP_CENTS", 2900),
                         ("market", "social", "news", "fundamentals"), _int("DEEP_DEBATE_ROUNDS", 3),
                         "about 20-45 minutes",
                         "Everything in Quick, plus sentiment and a multi-round bull-vs-bear evidence review."),
        }


def settings() -> Settings:
    return Settings()


def apply_report_branding(cfg: Settings | None = None) -> None:
    """Default the report generator's branding to BLMI unless already set."""
    cfg = cfg or settings()
    os.environ.setdefault("REPORT_BRAND", cfg.brand)
    os.environ.setdefault("REPORT_CONTACT", cfg.contact)
    os.environ.setdefault("REPORT_LOGO", str(STATIC_DIR / "blmi-logo.png"))
    os.environ.setdefault("REPORT_PRIMARY_COLOR", "#0b1e3f")
    os.environ.setdefault("REPORT_ACCENT_COLOR", "#f4811e")
    os.environ.setdefault("REPORT_HIGHLIGHT_COLOR", "#ffd166")
