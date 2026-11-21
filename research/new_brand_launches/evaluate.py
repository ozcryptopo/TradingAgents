"""Score the day-60 formula against the naive baselines (HYPOTHESES.md, H1-H3).

Numpy only: a small L2-regularized logistic regression, rank-based AUC,
precision in the top slice, and a bootstrap for the AUC gain.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .study import FEATURES

BASELINES = {"B30": "n_30_rank", "B60": "n_60_rank"}

MIN_TEST_DEBUTS = 300
MIN_TEST_SUCCESSES = 30
MIN_AUC_GAIN = 0.03
MIN_PRECISION_RATIO = 1.2
TOP_FRACTION = 0.10
BOOTSTRAPS = 1000


def auc(y: np.ndarray, score: np.ndarray) -> float:
    """Area under the ROC curve via the rank-sum formula (ties count half)."""
    y = np.asarray(y).astype(bool)
    n_pos, n_neg = int(y.sum()), int((~y).sum())
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    ranks = pd.Series(score).rank(method="average").to_numpy()
    return float((ranks[y].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg))


def precision_at(y: np.ndarray, score: np.ndarray, fraction: float = TOP_FRACTION) -> float:
    """Share of successes among the top ``fraction`` of debuts by score."""
    y = np.asarray(y)
    k = max(1, math.ceil(fraction * len(y)))
    # Ties (common in count ranks) are broken at random with a fixed seed, so
    # row order can never decide who lands in the top slice.
    tiebreak = np.random.default_rng(0).random(len(y))
    top = np.lexsort((tiebreak, -np.asarray(score, dtype=float)))[:k]
    return float(y[top].mean())


@dataclass
class Logistic:
    """L2-regularized logistic regression fitted by Newton's method."""

    l2: float = 1.0
    max_iter: int = 50
    mean_: np.ndarray = field(default=None, repr=False)
    std_: np.ndarray = field(default=None, repr=False)
    coef_: np.ndarray = field(default=None, repr=False)

    def _design(self, x: np.ndarray) -> np.ndarray:
        z = (x - self.mean_) / self.std_
        return np.column_stack([np.ones(len(z)), z])

    def fit(self, x: np.ndarray, y: np.ndarray) -> Logistic:
        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)
        self.mean_ = x.mean(axis=0)
        self.std_ = x.std(axis=0)
        self.std_[self.std_ == 0] = 1.0
        a = self._design(x)
        w = np.zeros(a.shape[1])
        penalty = np.full(a.shape[1], self.l2)
        penalty[0] = 0.0  # never shrink the intercept
        for _ in range(self.max_iter):
            p = 1 / (1 + np.exp(-(a @ w)))
            grad = a.T @ (p - y) + penalty * w
            hess = (a * (p * (1 - p))[:, None]).T @ a + np.diag(penalty)
            step = np.linalg.solve(hess, grad)
            w -= step
            if np.max(np.abs(step)) < 1e-8:
                break
        self.coef_ = w
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        return 1 / (1 + np.exp(-(self._design(np.asarray(x, dtype=float)) @ self.coef_)))


def rank_columns() -> list[str]:
    return [f"{f}_rank" for f in FEATURES]


def bootstrap_auc_gain(
    y: np.ndarray, model: np.ndarray, baseline: np.ndarray, n: int = BOOTSTRAPS, seed: int = 0
) -> tuple[float, float]:
    """95% interval of AUC(model) - AUC(baseline), resampling debuts."""
    rng = np.random.default_rng(seed)
    y, model, baseline = np.asarray(y), np.asarray(model), np.asarray(baseline)
    gains = []
    for _ in range(n):
        idx = rng.integers(0, len(y), len(y))
        if y[idx].min() == y[idx].max():
            continue
        gains.append(auc(y[idx], model[idx]) - auc(y[idx], baseline[idx]))
    if not gains:
        return float("nan"), float("nan")
    lo, hi = np.percentile(gains, [2.5, 97.5])
    return float(lo), float(hi)


def split(df: pd.DataFrame, train_last_year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    return df[df["launch_year"] <= train_last_year], df[df["launch_year"] > train_last_year]


def primary_test(df: pd.DataFrame, train_last_year: int = 2018, bootstraps: int = BOOTSTRAPS) -> dict:
    """H1: does the formula beat the naive baselines on later launches?"""
    train, test = split(df, train_last_year)
    result = {
        "train_debuts": len(train),
        "train_successes": int(train["success"].sum()) if len(train) else 0,
        "test_debuts": len(test),
        "test_successes": int(test["success"].sum()) if len(test) else 0,
    }
    if (
        len(test) < MIN_TEST_DEBUTS
        or result["test_successes"] < MIN_TEST_SUCCESSES
        or len(train) == 0
        or train["success"].nunique() < 2
    ):
        result["verdict"] = "INCONCLUSIVE"
        result["reason"] = (
            f"need at least {MIN_TEST_DEBUTS} test debuts and {MIN_TEST_SUCCESSES} test "
            "successes, plus both outcomes in training"
        )
        return result

    cols = rank_columns()
    model = Logistic().fit(train[cols].to_numpy(), train["success"].to_numpy())
    y = test["success"].to_numpy()
    scores = {"MODEL": model.predict(test[cols].to_numpy())}
    for name, col in BASELINES.items():
        scores[name] = test[col].to_numpy()

    metrics = {name: {"auc": auc(y, s), "precision_top10": precision_at(y, s)} for name, s in scores.items()}
    best = max(BASELINES, key=lambda b: metrics[b]["auc"])
    gain = metrics["MODEL"]["auc"] - metrics[best]["auc"]
    lo, hi = bootstrap_auc_gain(y, scores["MODEL"], scores[best], n=bootstraps)
    base_prec = metrics[best]["precision_top10"]
    prec_ratio = metrics["MODEL"]["precision_top10"] / base_prec if base_prec > 0 else float("inf")

    checks = {
        "auc_gain_at_least_0.03": gain >= MIN_AUC_GAIN,
        "auc_gain_interval_above_0": lo > 0,
        "precision_ratio_at_least_1.2": prec_ratio >= MIN_PRECISION_RATIO,
    }
    result.update(
        metrics=metrics,
        best_baseline=best,
        auc_gain=gain,
        auc_gain_interval=(lo, hi),
        precision_ratio=prec_ratio,
        checks=checks,
        coefficients=dict(zip(["intercept", *FEATURES], model.coef_.round(4).tolist(), strict=True)),
        verdict="PASS" if all(checks.values()) else "FAIL",
    )
    return result


def _tercile(rank: pd.Series) -> pd.Series:
    return pd.cut(rank, [0, 1 / 3, 2 / 3, 1.0], labels=["low", "mid", "high"], include_lowest=True)


def secondary_tests(df: pd.DataFrame) -> dict:
    """H2 and H3: success rates across terciles, reported without pass/fail."""
    out: dict = {}
    if df.empty:
        return out
    out["H2_neg_share"] = df.groupby(_tercile(df["neg_share_rank"]), observed=False)["success"].mean().to_dict()

    volume = _tercile(df["n_60_rank"])
    h3 = {}
    for col in ("new_account_share", "burst_share"):
        level = _tercile(df[f"{col}_rank"])
        table = df.groupby([volume, level], observed=False)["success"].mean().unstack()
        h3[col] = table.round(4).to_dict(orient="index")
    table = df.groupby([volume, df["no_negatives"]], observed=False)["success"].mean().unstack()
    h3["no_negatives"] = table.round(4).to_dict(orient="index")
    out["H3_by_volume_tercile"] = h3

    out["single_feature_auc"] = {
        f: round(auc(df["success"].to_numpy(), df[f"{f}_rank"].to_numpy()), 4) for f in FEATURES
    }
    return out
