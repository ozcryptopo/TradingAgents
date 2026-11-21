"""Download and load the UCSD Amazon Reviews 2023 category files.

Only the columns the study needs are kept, so a category with millions of
reviews fits in memory. Helpful votes and the metadata's rating summary are
dropped on purpose: they are snapshots from the 2023 crawl and would leak the
future into a point-in-time feature.
"""

from __future__ import annotations

import gzip
import json
import os
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

# The McAuley Lab hosts the raw files; override with AMAZON_REVIEWS_BASE_URL if
# the lab moves them.
DEFAULT_BASE_URL = "https://mcauleylab.ucsd.edu/public_datasets/data/amazon_2023/raw"

UNKNOWN_STORES = {"", "unknown", "none", "n/a", "na", "generic"}


def base_url() -> str:
    return os.environ.get("AMAZON_REVIEWS_BASE_URL", DEFAULT_BASE_URL).rstrip("/")


def file_urls(category: str) -> dict[str, str]:
    root = base_url()
    return {
        "reviews": f"{root}/review_categories/{category}.jsonl.gz",
        "meta": f"{root}/meta_categories/meta_{category}.jsonl.gz",
    }


def local_paths(category: str, data_dir: str | Path) -> dict[str, Path]:
    data_dir = Path(data_dir)
    return {
        "reviews": data_dir / f"{category}.jsonl.gz",
        "meta": data_dir / f"meta_{category}.jsonl.gz",
    }


def download_category(category: str, data_dir: str | Path, timeout: int = 60) -> dict[str, Path]:
    """Fetch a category's review and metadata files unless already on disk."""
    import requests

    paths = local_paths(category, data_dir)
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    for kind, url in file_urls(category).items():
        dest = paths[kind]
        if dest.exists() and dest.stat().st_size > 0:
            continue
        partial = dest.with_suffix(dest.suffix + ".part")
        with requests.get(url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            with open(partial, "wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 20):
                    fh.write(chunk)
        partial.rename(dest)
    return paths


def _iter_jsonl(path: str | Path) -> Iterator[dict]:
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                yield json.loads(line)


def normalize_store(value) -> str:
    if not isinstance(value, str):
        return ""
    store = " ".join(value.lower().split())
    return "" if store in UNKNOWN_STORES else store


def load_meta(path: str | Path, category: str) -> pd.DataFrame:
    """One row per product: parent_asin, brand (normalized store), category, title."""
    rows = [
        (rec.get("parent_asin"), normalize_store(rec.get("store")), rec.get("title") or "")
        for rec in _iter_jsonl(path)
    ]
    meta = pd.DataFrame(rows, columns=["parent_asin", "brand", "title"])
    meta = meta[meta["parent_asin"].notna() & (meta["brand"] != "")]
    meta = meta.drop_duplicates("parent_asin")
    meta["category"] = category
    return meta.reset_index(drop=True)


def load_reviews(path: str | Path, keep_asins: set[str] | None = None) -> pd.DataFrame:
    """Compact review table: parent_asin, user_id, ts, rating, verified.

    ``keep_asins`` limits memory to products of interest. Reviews from every
    product are still needed to count a reviewer's earlier reviews, so pass
    None when computing ``new_account_share`` over the whole category.
    """
    asins, users, stamps, ratings, verified = [], [], [], [], []
    for rec in _iter_jsonl(path):
        asin = rec.get("parent_asin")
        if asin is None or (keep_asins is not None and asin not in keep_asins):
            continue
        asins.append(asin)
        users.append(rec.get("user_id") or "")
        stamps.append(rec.get("timestamp"))
        ratings.append(rec.get("rating"))
        verified.append(bool(rec.get("verified_purchase")))
    reviews = pd.DataFrame(
        {
            "parent_asin": asins,
            "user_id": users,
            "ts": pd.to_datetime(stamps, unit="ms", utc=True),
            "rating": pd.to_numeric(ratings, errors="coerce"),
            "verified": verified,
        }
    )
    reviews = reviews.dropna(subset=["ts", "rating"])
    reviews["rating"] = reviews["rating"].round().clip(1, 5).astype("int8")
    return reviews.reset_index(drop=True)
