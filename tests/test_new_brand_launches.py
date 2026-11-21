"""Tests for the new-brand launch study, on synthetic data only."""

import gzip
import json

import numpy as np
import pandas as pd
import pytest

from research.new_brand_launches import data, evaluate, run, study


def _ts(day: str, offset_days: float = 0) -> pd.Timestamp:
    return pd.Timestamp(day, tz="UTC") + pd.Timedelta(days=offset_days)


def _reviews(rows):
    df = pd.DataFrame(rows, columns=["parent_asin", "user_id", "ts", "rating", "verified"])
    df["rating"] = df["rating"].astype("int8")
    return df


def _meta(rows, category="Cat"):
    df = pd.DataFrame(rows, columns=["parent_asin", "brand"])
    df["title"] = ""
    df["category"] = category
    return df


# --- data loading -----------------------------------------------------------


def test_load_files_keep_needed_columns_and_drop_unknown_brands(tmp_path):
    meta_path = tmp_path / "meta_Cat.jsonl.gz"
    with gzip.open(meta_path, "wt") as fh:
        fh.write(json.dumps({"parent_asin": "A", "store": "  Acme  Co ", "title": "x", "average_rating": 4.9}) + "\n")
        fh.write(json.dumps({"parent_asin": "B", "store": "Unknown"}) + "\n")
        fh.write(json.dumps({"parent_asin": "C", "store": None}) + "\n")
    reviews_path = tmp_path / "Cat.jsonl.gz"
    with gzip.open(reviews_path, "wt") as fh:
        fh.write(json.dumps({"parent_asin": "A", "user_id": "u1", "timestamp": 1_600_000_000_000,
                             "rating": 4.0, "verified_purchase": True, "helpful_vote": 9}) + "\n")
        fh.write(json.dumps({"parent_asin": "B", "user_id": "u2", "timestamp": 1_600_000_000_000,
                             "rating": 1.0, "verified_purchase": False}) + "\n")

    meta = data.load_meta(meta_path, "Cat")
    assert meta["parent_asin"].tolist() == ["A"]
    assert meta["brand"].tolist() == ["acme co"]
    assert "average_rating" not in meta.columns  # 2023 snapshot: look-ahead

    reviews = data.load_reviews(reviews_path, keep_asins={"A"})
    assert reviews["parent_asin"].tolist() == ["A"]
    assert list(reviews.columns) == ["parent_asin", "user_id", "ts", "rating", "verified"]
    assert "helpful_vote" not in reviews.columns  # 2023 snapshot: look-ahead
    assert reviews["ts"].iloc[0] == pd.Timestamp(1_600_000_000_000, unit="ms", tz="UTC")


def test_base_url_can_be_overridden(monkeypatch):
    monkeypatch.setenv("AMAZON_REVIEWS_BASE_URL", "https://mirror.example/raw/")
    assert data.file_urls("All_Beauty")["meta"] == "https://mirror.example/raw/meta_categories/meta_All_Beauty.jsonl.gz"


# --- debut detection ----------------------------------------------------------


def test_debut_is_brands_first_product_and_ambiguous_brands_are_dropped():
    meta = _meta([("A1", "solo"), ("A2", "solo"), ("B1", "twins"), ("B2", "twins"), ("C1", "old")])
    reviews = _reviews([
        ("A1", "u", _ts("2018-03-01"), 5, True),
        ("A2", "u", _ts("2018-09-01"), 5, True),   # 184 days later: debut stays clear
        ("B1", "u", _ts("2018-03-01"), 5, True),
        ("B2", "u", _ts("2018-04-01"), 5, True),   # 31 days later: ambiguous brand
        ("C1", "u", _ts("2014-01-01"), 5, True),   # before the launch window
    ])
    debuts = study.find_debuts(reviews, meta)
    assert debuts["parent_asin"].tolist() == ["A1"]
    assert debuts["cohort"].tolist() == ["Cat:2018"]


# --- features -----------------------------------------------------------------


def test_prior_review_counts_never_look_ahead():
    reviews = _reviews([
        ("P", "u1", _ts("2018-01-05"), 5, True),
        ("Q", "u1", _ts("2018-01-01"), 5, True),
        ("P", "", _ts("2018-01-02"), 5, True),
    ])
    out = study.add_prior_review_counts(reviews).set_index(["parent_asin", "user_id"])
    assert out.loc[("Q", "u1"), "prior_reviews"] == 0
    assert out.loc[("P", "u1"), "prior_reviews"] == 1
    assert np.isnan(out.loc[("P", ""), "prior_reviews"])


def test_day_60_features_and_months_7_to_12_outcome():
    launch = "2018-01-01"
    rows = [
        ("A", "a0", _ts(launch, 0), 5, True),
        ("A", "a1", _ts(launch, 0.5), 5, False),   # same day as the first: burst of 2
        ("A", "a2", _ts(launch, 10), 1, True),
        ("A", "a3", _ts(launch, 40), 4, True),
        ("A", "a4", _ts(launch, 59), 2, True),
        ("A", "a5", _ts(launch, 61), 1, True),     # after the cutoff: not a feature
        ("A", "a6", _ts(launch, 200), 5, True),    # outcome window
        ("A", "a7", _ts(launch, 364), 5, True),    # outcome window
        ("A", "a8", _ts(launch, 366), 5, True),    # after the outcome window
        ("Z", "a2", _ts("2017-06-01"), 5, True),   # gives a2 an earlier review
        ("Z", "z", _ts("2020-01-01"), 5, True),    # data runs past launch + 365
    ]
    reviews = study.add_prior_review_counts(_reviews(rows))
    meta = _meta([("A", "acme"), ("Z", "zed")])
    debuts = study.find_debuts(reviews, meta)
    feats = study.build_features(reviews, debuts).set_index("parent_asin").loc["A"]

    assert feats["n_30"] == 3
    assert feats["n_60"] == 5
    assert feats["growth"] == pytest.approx(np.log1p(2) - np.log1p(3))
    assert feats["avg_rating"] == pytest.approx((5 + 5 + 1 + 4 + 2) / 5)
    assert feats["neg_share"] == pytest.approx(2 / 5)
    assert feats["five_share"] == pytest.approx(2 / 5)
    assert feats["unverified_share"] == pytest.approx(1 / 5)
    assert feats["new_account_share"] == pytest.approx(4 / 5)
    assert feats["burst_share"] == pytest.approx(2 / 5)
    assert feats["no_negatives"] == 0
    assert feats["later_reviews"] == 2


def test_debuts_without_a_full_year_of_data_are_dropped():
    reviews = study.add_prior_review_counts(_reviews([("A", "u", _ts("2021-06-01"), 5, True)]))
    debuts = study.find_debuts(reviews, _meta([("A", "acme")]))
    assert study.build_features(reviews, debuts).empty


def test_success_is_top_decile_within_cohort_and_small_cohorts_dropped():
    n = 30
    big = pd.DataFrame({
        "parent_asin": [f"b{i}" for i in range(n)],
        "cohort": "Cat:2018",
        "later_reviews": list(range(n)),
        **{f: np.arange(n, dtype=float) for f in study.FEATURES},
    })
    small = big.head(5).assign(parent_asin=lambda d: "s" + d["parent_asin"], cohort="Cat:2019")
    ranked = study.label_and_rank(pd.concat([big, small]))
    assert set(ranked["cohort"]) == {"Cat:2018"}
    assert ranked.loc[ranked["success"] == 1, "later_reviews"].tolist() == [27, 28, 29]


# --- evaluation ---------------------------------------------------------------


def test_auc_and_precision():
    y = np.array([0, 0, 1, 1])
    assert evaluate.auc(y, np.array([0.1, 0.2, 0.3, 0.4])) == 1.0
    assert evaluate.auc(y, np.array([0.4, 0.3, 0.2, 0.1])) == 0.0
    assert evaluate.auc(y, np.ones(4)) == 0.5
    assert np.isnan(evaluate.auc(np.ones(4), np.arange(4)))
    assert evaluate.precision_at(np.array([1] + [0] * 9), np.arange(10)[::-1], 0.1) == 1.0


def test_logistic_regression_learns_the_direction_of_a_signal():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(2000, 2))
    y = (rng.random(2000) < 1 / (1 + np.exp(-(2 * x[:, 0] - 1)))).astype(int)
    model = evaluate.Logistic().fit(x, y)
    assert model.coef_[1] > 1.0
    assert abs(model.coef_[2]) < 0.3
    assert evaluate.auc(y, model.predict(x)) > 0.75


def _synthetic_study(signal: bool, n_per_year: int = 400, seed: int = 0) -> pd.DataFrame:
    """Ranked debuts where success depends on early volume and, if ``signal``,
    also on the share of bad reviews, which the volume baselines cannot see."""
    rng = np.random.default_rng(seed)
    frames = []
    for year in range(2016, 2022):
        n = n_per_year
        df = pd.DataFrame({f: rng.random(n) for f in study.FEATURES})
        df["parent_asin"] = [f"{year}-{i}" for i in range(n)]
        df["cohort"] = f"Cat:{year}"
        df["launch_year"] = year
        logit = 2.0 * df["n_60"] - 3.0 + (-4.0 * (df["neg_share"] - 0.5) if signal else 0)
        df["later_reviews"] = (rng.random(n) < 1 / (1 + np.exp(-logit))).astype(int) * rng.integers(50, 100, n)
        df["later_reviews"] += rng.integers(0, 5, n)
        frames.append(df)
    return study.label_and_rank(pd.concat(frames, ignore_index=True))


def test_primary_test_passes_when_reviews_carry_information_beyond_volume():
    result = evaluate.primary_test(_synthetic_study(signal=True), bootstraps=200)
    assert result["verdict"] == "PASS", result
    assert result["coefficients"]["neg_share"] < 0


def test_primary_test_fails_when_only_volume_matters():
    result = evaluate.primary_test(_synthetic_study(signal=False), bootstraps=200)
    assert result["verdict"] == "FAIL", result


def test_primary_test_is_inconclusive_on_too_little_data():
    result = evaluate.primary_test(_synthetic_study(signal=True, n_per_year=40), bootstraps=50)
    assert result["verdict"] == "INCONCLUSIVE"


# --- end to end ---------------------------------------------------------------


def test_run_end_to_end_on_synthetic_reviews():
    rng = np.random.default_rng(3)
    meta_rows, review_rows = [], []
    for year in (2017, 2019):
        for i in range(25):
            asin = f"{year}-{i}"
            meta_rows.append((asin, f"brand-{asin}"))
            launch = _ts(f"{year}-03-01")
            for d in sorted(rng.integers(0, 365, rng.integers(1, 40))):
                review_rows.append((asin, f"u{rng.integers(0, 500)}", launch + pd.Timedelta(days=int(d)),
                                    int(rng.integers(1, 6)), True))
            review_rows.insert(0, (asin, "first", launch, 5, True))
    review_rows.append(("tail", "t", _ts("2023-01-01"), 5, True))
    ranked, results = run.run(_meta(meta_rows), _reviews(review_rows), bootstraps=20)

    assert results["debuts_found"] == 50
    assert results["debuts_in_cohorts"] == 50
    assert results["primary"]["verdict"] == "INCONCLUSIVE"  # 25 test debuts is too few
    assert set(results["secondary"]["single_feature_auc"]) == set(study.FEATURES)
    report = run.render_report(results, ["Cat"])
    assert "H1 verdict: **INCONCLUSIVE**" in report
