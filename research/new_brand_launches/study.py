"""Find each new brand's debut product and measure it at day 60.

Everything here follows HYPOTHESES.md. A feature may only use reviews dated
before the cutoff; the outcome only uses reviews from days 180 to 364.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = [
    "n_30",
    "n_60",
    "growth",
    "avg_rating",
    "neg_share",
    "five_share",
    "no_negatives",
    "unverified_share",
    "new_account_share",
    "burst_share",
]

OUTCOME_START_DAY = 180
OUTCOME_END_DAY = 365  # exclusive
MIN_COHORT_SIZE = 20
SUCCESS_TOP_FRACTION = 0.10


def add_prior_review_counts(reviews: pd.DataFrame) -> pd.DataFrame:
    """Add ``prior_reviews``: how many earlier reviews the same account wrote.

    Counted only from reviews dated earlier, so it is safe to use at any
    cutoff. Reviews without a user id get NaN.
    """
    out = reviews.sort_values(["ts", "parent_asin"], kind="stable").copy()
    has_user = out["user_id"].astype(str) != ""
    out["prior_reviews"] = np.nan
    out.loc[has_user, "prior_reviews"] = out[has_user].groupby("user_id").cumcount()
    return out


def find_debuts(
    reviews: pd.DataFrame,
    meta: pd.DataFrame,
    launch_start: str = "2016-01-01",
    launch_end: str = "2021-12-31",
    exclusivity_days: int = 90,
) -> pd.DataFrame:
    """One row per brand: its debut product, launch date, category and cohort."""
    first_review = reviews.groupby("parent_asin")["ts"].min().rename("launch")
    products = meta.merge(first_review, left_on="parent_asin", right_index=True)
    if products.empty:
        return products.assign(launch_year=pd.Series(dtype=int), cohort=pd.Series(dtype=str))

    brand_launch = products.groupby("brand")["launch"].transform("min")
    window = pd.Timedelta(days=exclusivity_days)
    in_window = products["launch"] < brand_launch + window
    products_in_window = products[in_window].groupby("brand")["parent_asin"].nunique()
    clean_brands = products_in_window[products_in_window == 1].index

    debuts = products[(products["launch"] == brand_launch) & products["brand"].isin(clean_brands)]
    start = pd.Timestamp(launch_start, tz="UTC")
    end = pd.Timestamp(launch_end, tz="UTC") + pd.Timedelta(days=1)
    debuts = debuts[(debuts["launch"] >= start) & (debuts["launch"] < end)].copy()
    debuts["launch_year"] = debuts["launch"].dt.year
    debuts["cohort"] = debuts["category"] + ":" + debuts["launch_year"].astype(str)
    return debuts.reset_index(drop=True)


def build_features(
    reviews: pd.DataFrame,
    debuts: pd.DataFrame,
    cutoff_days: int = 60,
) -> pd.DataFrame:
    """Day-``cutoff_days`` features and the months 7-12 outcome for each debut.

    ``reviews`` should already carry ``prior_reviews`` (see
    add_prior_review_counts). Debuts whose outcome window runs past the end of
    the data are dropped, since their outcome is not yet known.
    """
    data_end = reviews["ts"].max()
    debuts = debuts[debuts["launch"] + pd.Timedelta(days=OUTCOME_END_DAY) <= data_end]
    if debuts.empty:
        return pd.DataFrame(columns=["parent_asin", *FEATURES, "later_reviews"])

    r = reviews.merge(debuts[["parent_asin", "launch"]], on="parent_asin")
    r["age"] = (r["ts"] - r["launch"]).dt.total_seconds() / 86400.0

    early = r[r["age"] < cutoff_days].copy()
    half = cutoff_days / 2
    early["first_half"] = early["age"] < half
    early["neg"] = early["rating"] <= 2
    early["five"] = early["rating"] == 5
    early["unverified"] = ~early["verified"].astype(bool)
    early["new_account"] = early["prior_reviews"] == 0
    early["day"] = early["age"].astype(int)

    grouped = early.groupby("parent_asin")
    feats = pd.DataFrame(
        {
            "n_30": grouped["first_half"].sum(),
            "n_60": grouped.size(),
            "avg_rating": grouped["rating"].mean(),
            "neg_share": grouped["neg"].mean(),
            "five_share": grouped["five"].mean(),
            "unverified_share": grouped["unverified"].mean(),
            "new_account_share": grouped["new_account"].mean(),
        }
    )
    second_half = feats["n_60"] - feats["n_30"]
    feats["growth"] = np.log1p(second_half) - np.log1p(feats["n_30"])
    feats["no_negatives"] = ((feats["n_60"] >= 10) & (feats["neg_share"] == 0)).astype(int)
    max_day = early.groupby(["parent_asin", "day"]).size().groupby("parent_asin").max()
    feats["burst_share"] = max_day / feats["n_60"]

    later = r[(r["age"] >= OUTCOME_START_DAY) & (r["age"] < OUTCOME_END_DAY)]
    feats["later_reviews"] = later.groupby("parent_asin").size()
    feats["later_reviews"] = feats["later_reviews"].fillna(0).astype(int)

    feats = feats.reset_index()
    keep = ["parent_asin", "brand", "category", "launch", "launch_year", "cohort", "title"]
    out = debuts[[c for c in keep if c in debuts.columns]].merge(feats, on="parent_asin")
    return out[["parent_asin", *[c for c in keep[1:] if c in out.columns], *FEATURES, "later_reviews"]]


def label_and_rank(features: pd.DataFrame, min_cohort: int = MIN_COHORT_SIZE) -> pd.DataFrame:
    """Rank every feature within its cohort and mark the top-decile successes."""
    sizes = features.groupby("cohort")["parent_asin"].transform("size")
    df = features[sizes >= min_cohort].copy()
    if df.empty:
        return df.assign(success=pd.Series(dtype=int))
    by_cohort = df.groupby("cohort")
    for col in FEATURES:
        df[f"{col}_rank"] = by_cohort[col].rank(pct=True, method="average")
    later_rank = by_cohort["later_reviews"].rank(pct=True, method="average")
    df["success"] = ((later_rank > 1 - SUCCESS_TOP_FRACTION) & (df["later_reviews"] > 0)).astype(int)
    return df.reset_index(drop=True)
