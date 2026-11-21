# New-brand launch study

Can a new brand's first Amazon product be judged at day 60? This study checks
whether early review signals predict which debut products are still selling
well 6 to 12 months later, better than the naive guess that "it started
fast". The criteria are fixed in advance in [HYPOTHESES.md](HYPOTHESES.md).

## What it does

1. **Loads** the UCSD Amazon Reviews 2023 category files (`data.py`), keeping
   only point-in-time fields.
2. **Finds debuts** (`study.find_debuts`): each brand's first product launched
   2016 to 2021, where no other product of the brand launched within 90 days.
3. **Measures day 60** (`study.build_features`): review counts, growth, star
   mix, share of bad reviews, missing negatives, unverified share,
   first-time-reviewer share and single-day bursts.
4. **Labels the outcome** (`study.label_and_rank`): the top 10% of each
   category-and-year cohort by reviews in days 180 to 364.
5. **Tests** (`evaluate.py`): trains a logistic model on 2016 to 2018 debuts,
   scores 2019 to 2021 debuts, compares it with the day-30 and day-60 volume
   baselines, and returns PASS, FAIL or INCONCLUSIVE using the rules in
   HYPOTHESES.md. It also reports the H2 and H3 tables.

## Run it

```bash
pip install -e ".[dev]"
python -m research.new_brand_launches.run \
    --categories All_Beauty Health_and_Personal_Care Appliances Amazon_Fashion
```

Files download once into `research/new_brand_launches/data/`. Results go to
`results/report.md` and `results/debuts.csv`. Both folders are git-ignored.
Use `--no-download` to run on files already on disk, and set
`AMAZON_REVIEWS_BASE_URL` if the dataset moves.

Start with the small categories listed above. The large ones (for example
`Home_and_Kitchen`, with tens of millions of reviews) need far more memory.

Tests use synthetic data only:

```bash
python -m pytest tests/test_new_brand_launches.py
```

## Read results with care

- Reviews stand in for sales. A PASS justifies buying sales-rank history
  (for example from Keepa) to confirm with a real sales signal.
- The dataset is for research use only. A commercial product needs licensed
  data.
