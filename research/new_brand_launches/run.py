"""Run the new-brand launch study end to end.

    python -m research.new_brand_launches.run --categories All_Beauty Appliances

Downloads each category once into --data-dir, finds debut products, scores
them at day 60 and writes results/report.md plus the per-debut feature table.
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd

from . import data, evaluate, study

HERE = Path(__file__).resolve().parent
DEFAULT_CATEGORIES = ["All_Beauty", "Health_and_Personal_Care", "Appliances", "Amazon_Fashion"]


def load_categories(categories: list[str], data_dir: Path, download: bool) -> tuple[pd.DataFrame, pd.DataFrame]:
    metas, reviews = [], []
    for category in categories:
        paths = data.download_category(category, data_dir) if download else data.local_paths(category, data_dir)
        print(f"loading {category} ...", flush=True)
        metas.append(data.load_meta(paths["meta"], category))
        reviews.append(data.load_reviews(paths["reviews"]))
    return pd.concat(metas, ignore_index=True), pd.concat(reviews, ignore_index=True)


def run(
    meta: pd.DataFrame,
    reviews: pd.DataFrame,
    *,
    launch_start: str = "2016-01-01",
    launch_end: str = "2021-12-31",
    train_last_year: int = 2018,
    cutoff_days: int = 60,
    min_cohort: int = study.MIN_COHORT_SIZE,
    bootstraps: int = evaluate.BOOTSTRAPS,
) -> tuple[pd.DataFrame, dict]:
    reviews = study.add_prior_review_counts(reviews)
    debuts = study.find_debuts(reviews, meta, launch_start, launch_end)
    features = study.build_features(reviews, debuts, cutoff_days)
    ranked = study.label_and_rank(features, min_cohort)
    results = {
        "debuts_found": len(debuts),
        "debuts_with_known_outcome": len(features),
        "debuts_in_cohorts": len(ranked),
        "primary": evaluate.primary_test(ranked, train_last_year, bootstraps),
        "secondary": evaluate.secondary_tests(ranked),
    }
    return ranked, results


def render_report(results: dict, categories: list[str]) -> str:
    p = results["primary"]
    lines = [
        "# New-brand launch study: results",
        "",
        f"Run on {date.today().isoformat()} over: {', '.join(categories)}.",
        "Criteria are in HYPOTHESES.md and were fixed before this run.",
        "",
        f"## H1 verdict: **{p['verdict']}**",
        "",
        f"- Debuts found: {results['debuts_found']}; with a known 12-month outcome: "
        f"{results['debuts_with_known_outcome']}; in cohorts of 20+: {results['debuts_in_cohorts']}",
        f"- Train (launched up to the split year): {p['train_debuts']} debuts, {p['train_successes']} successes",
        f"- Test (launched later): {p['test_debuts']} debuts, {p['test_successes']} successes",
    ]
    if p["verdict"] == "INCONCLUSIVE":
        lines += ["", f"Not enough data: {p['reason']}."]
    else:
        lines += ["", "| Score | AUC | Precision in top 10% |", "|---|---|---|"]
        for name, m in p["metrics"].items():
            lines.append(f"| {name} | {m['auc']:.3f} | {m['precision_top10']:.3f} |")
        lo, hi = p["auc_gain_interval"]
        lines += [
            "",
            f"- Best baseline: {p['best_baseline']}",
            f"- AUC gain: {p['auc_gain']:+.3f} (95% interval {lo:+.3f} to {hi:+.3f})",
            f"- Precision ratio vs. best baseline: {p['precision_ratio']:.2f}",
            "",
            "Checks:",
            *[f"- {'✅' if ok else '❌'} {name}" for name, ok in p["checks"].items()],
            "",
            "Model coefficients (standardized cohort ranks):",
            "```json",
            json.dumps(p["coefficients"], indent=2),
            "```",
        ]
    lines += [
        "",
        "## Secondary results (H2, H3), reported only",
        "",
        "```json",
        json.dumps(results["secondary"], indent=2, default=str),
        "```",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--categories", nargs="+", default=DEFAULT_CATEGORIES)
    parser.add_argument("--data-dir", type=Path, default=HERE / "data")
    parser.add_argument("--out-dir", type=Path, default=HERE / "results")
    parser.add_argument("--no-download", action="store_true", help="use files already in --data-dir")
    parser.add_argument("--launch-start", default="2016-01-01")
    parser.add_argument("--launch-end", default="2021-12-31")
    parser.add_argument("--train-last-year", type=int, default=2018)
    args = parser.parse_args(argv)

    meta, reviews = load_categories(args.categories, args.data_dir, not args.no_download)
    ranked, results = run(
        meta,
        reviews,
        launch_start=args.launch_start,
        launch_end=args.launch_end,
        train_last_year=args.train_last_year,
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    ranked.to_csv(args.out_dir / "debuts.csv", index=False)
    report = render_report(results, args.categories)
    (args.out_dir / "report.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
