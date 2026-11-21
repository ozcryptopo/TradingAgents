# New-brand launch study: pre-registered hypotheses

**Registered:** 2026-11-21, before any real data was loaded.
Change this file only by adding a dated amendment at the bottom. Never edit a
criterion after results exist.

## Question

When a new brand's **first product** goes on sale on Amazon, can its first
60 days of review activity tell us whether it will still be selling well
6 to 12 months later? And can it tell us better than the obvious guess, which
is that products that started fast keep going?

## Definitions

| Term | Definition |
|---|---|
| Brand | The `store` field in the UCSD Amazon Reviews 2023 metadata, lower-cased and trimmed. Blank or "unknown" stores are dropped. |
| Product launch date | The date of the product's first review (proxy; true listing dates are not in the data). |
| Brand launch date | The earliest launch date among the brand's products. |
| Debut product | A brand's first product. A brand is kept only if no other product of its own launched within 90 days of the debut, so the debut is unambiguous. |
| Launch window | Debuts from 2016-01-01 through 2021-12-31. |
| Cohort | Debuts in the same dataset category and the same launch year. Every feature and the outcome are ranked within the cohort. Cohorts with fewer than 20 debuts are dropped, since ranks in them are too noisy. |
| Cutoff | Day 60 after launch. Features use only reviews dated before the cutoff. |
| Outcome ("success") | Reviews received in days 180 to 364 after launch, in the top 10% of the cohort. This is a proxy for sustained sales in months 7 to 12, and it skips the launch burst that sellers can seed. |

## Features (day 60, point in time)

- `n_30`, `n_60`: review counts by day 30 and day 60
- `growth`: log ratio of reviews in days 30 to 59 vs. days 0 to 29
- `avg_rating`: mean star rating
- `neg_share`: share of 1 and 2-star reviews
- `five_share`: share of 5-star reviews
- `no_negatives`: 1 if there are at least 10 reviews and none are 1 or 2 stars
- `unverified_share`: share of reviews not marked verified purchase
- `new_account_share`: share of reviews that were the reviewer account's first review in the category (counted only from earlier reviews, so no look-ahead)
- `burst_share`: the largest single day's reviews divided by `n_60`

Excluded because they would leak the future: helpful votes and the
metadata's average rating and rating count. All three are snapshots taken
when the dataset was collected in 2023.

## Primary hypothesis (H1): pass/fail

A logistic model over the cohort-ranked features predicts success better than
the best naive baseline.

- Baselines: **B30** = cohort rank of `n_30`; **B60** = cohort rank of `n_60`.
- Train on 2016 to 2018 debuts and test on 2019 to 2021 debuts. All numbers
  below are on the test set.
- **PASS** only if all of these hold:
  1. AUC(model) minus AUC(best baseline) ≥ 0.03
  2. The 95% bootstrap interval of that AUC gain is above 0 (1,000 resamples)
  3. Precision in the top 10% for the model ≥ 1.2 × the best baseline's
- **INCONCLUSIVE** if the test set has fewer than 300 debuts or fewer than
  30 successes.
- Otherwise **FAIL**. A fail means the formula adds nothing beyond "it
  started fast", so it is not worth selling.

## Secondary hypotheses (reported only, not pass/fail)

- **H2 (bad reviews):** debuts in the top third of their cohort by
  `neg_share` succeed less often than those in the bottom third.
- **H3 (signs of fake reviews):** among debuts with similar `n_60`, a high
  `new_account_share`, a high `burst_share` or `no_negatives = 1` goes with
  lower success. Measured as the success rate within `n_60` terciles.

## Known limitations, stated in advance

- **Reviews stand in for sales.** There is no sales-rank history in the
  dataset. A pass justifies buying sales-rank history (e.g. from Keepa) to
  confirm with a sales measure that reviews cannot inflate.
- **Products with zero reviews are invisible**, so the worst failures are
  missing from the data.
- **No Vine flag** in the 2023 data, so seeded Vine reviews cannot be
  separated out.
- **First review date is not the listing date.** A slow seller's true launch
  may be earlier than recorded.
- **License:** the UCSD dataset is for research use. A commercial product
  needs licensed data.

## Amendments

_None yet._
