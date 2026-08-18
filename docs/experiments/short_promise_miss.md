# Experiment: train miss only on short promises

Date: 2026-08-18  
Script: `scripts/experiment_short_promise_miss.py`  
Question: are padded long ETAs drowning miss signal by filling the train set with almost-never-late orders?

Time split first, then filter on `estimated_delivery_horizon_days`, so the calendar window is unchanged. Production features; y = `promise_miss`.

## Test miss rate by promised horizon

Later-period test (`n=14,471`, overall miss **4.8%**):

| Horizon | n | Miss rate |
|---|---:|---:|
| ≤7d | 123 | 13.8% |
| 7–10d | 748 | 6.7% |
| 10–14d | 1,333 | 5.5% |
| 14–18d | 1,882 | 8.5% |
| 18–21d | 1,775 | 8.3% |
| 21–30d | 4,831 | 4.3% |
| 30–45d | 3,283 | 1.2% |
| >45d | 496 | 0.4% |

Long promises really are almost never late. Very short promises are rare in the **train** window (≤7d: only 35 train rows) — not a viable population by themselves.

## Does training on long promises kill short-promise ranking?

Same **short** test slice; two trainers.

| Eval population | Train short only | Train all rows |
|---|---|---|
| ≤10d test (base 7.7%) | PR-AUC 0.11 / ROC 0.63 | **0.12 / 0.58** |
| ≤14d (base 6.4%) | 0.10 / 0.60 | **0.11 / 0.62** |
| ≤18d (base 7.3%) | **0.16 / 0.66** | 0.14 / 0.65 |
| ≤21d (base 7.6%) | 0.14 / 0.66 | **0.18 / 0.67** |
| ≤30d (base 6.1%) | 0.18 / 0.72 | **0.19 / 0.73** |
| All test (base 4.8%) | — | 0.18 / **0.75** |

Training on everyone is as good or **better** on the short-promise cases. The extra long-promise rows are not poisoning the ranker; they add seller/geo volume.

## What the long promises *are* doing

They inflate **ROC on the full test set**. Overall ROC **0.75** vs **0.60–0.67** when you only score short/medium promises. The model gets a lot of ranking credit for “this 35-day ETA will not miss,” which is easy and not an operational win.

Restricting the population to short promises does **not** uncover a hidden strong model. It removes easy negatives and leaves a weaker, higher-base-rate problem (prec@10% still ~11–19%).

## Decision

Do not filter the train set to short ETAs as a salvage. The miss problem is hard **on the orders that could actually miss**. Long ETAs are easy negatives, not label noise.

Reproduce:

```bash
uv run python scripts/experiment_short_promise_miss.py
```
