# Experiment: early vs promise, and day-delta regression

Date: 2026-08-18  
Script: `scripts/experiment_early_delta.py`  
Production features, temporal test `n=14,471`. Champion unchanged.

## Distribution (test)

| | |
|---|---:|
| Arrives **before** promise | **95.2%** |
| Same calendar day | 0.9% |
| After promise (late) | **4.8%** |
| ≥3 days early | 92.1% |
| ≥7 days early | 80.3% |
| ≥14 days early | **49.7%** |
| Mean / median days early | 14.5 / 13.9 |
| p10 / p90 days early | 4.1 / 27.1 |

Olist does not have a close-to-promise process. The typical order beats the ETA by two weeks. “Will it arrive before the promise?” is almost the constant `yes`.

## Binary: before promise

| Target | Base | PR-AUC (dummy = base) | ROC | Prec@10% |
|---|---:|---:|---:|---:|
| is_early | 95.2% | 0.983 (0.952) | 0.76 | 99.9% |
| is_late (same problem flipped) | 4.8% | 0.176 (0.048) | 0.75 | 15.9% |
| early ≥7d | 80.3% | 0.959 (0.803) | 0.86 | 99.3% |
| early ≥14d | 49.7% | 0.927 (0.497) | **0.94** | 97.5% |

`is_early` ROC matches `is_late`. The 0.98 PR-AUC is the majority class, not a new signal.

`early ≥14d` looks strong **because the promise length is in X**. Same classifiers with horizon **removed**:

| Target | Base | PR-AUC | ROC | Prec@10% |
|---|---:|---:|---:|---:|
| early ≥7d, no horizon | 80.3% | 0.878 | 0.66 | 92.4% |
| early ≥14d, no horizon | 49.7% | 0.624 | 0.68 | 63.6% |

So “will we beat the ETA by two weeks?” is mostly “did we quote a long ETA?” Without the quote, it is a moderate duration problem (lift 1.3× at 10% capacity vs 50% base).

## Regression: promise − actual (signed and absolute)

Naive = always predict the train mean.

| Target | MAE | vs naive | R² | corr |
|---|---:|---:|---:|---:|
| `days_early` (signed) | 4.75d | −3.06d | 0.56 | 0.79 |
| implied: `horizon − pred(duration)` | **4.65d** | −3.16d | **0.59** | 0.80 |
| `abs(promise − actual)` | 3.96d | −3.00d | 0.65 | 0.84 |
| duration itself | 4.65d | −1.92d | 0.24 | 0.56 |

Absolute delta looks best because 95% of mass is “how early”; `|delta| ≈ days_early`. Signed residual and duration-then-subtract are the same physical model we already ran in `overrun_duration.md`.

Calibration-style: signed model is within 3 days **39%** of the time (naive 27%), within 7 days **79%** (naive 56%). Sign match is 95% only because almost everything is early and the model almost always predicts early.

## How to read this for the product

- **Before vs after the promise** is not a new task. It is miss with the labels flipped, 95% “before.”
- **Day delta is learnable** at about **±5 days MAE**, R² ~0.6. That is real. The action it supports is **ETA recalibration** (“we’ll probably land ~12 days before the quoted date”), not “this order will fail an SLA.”
- **Absolute delta** does not add a second phenomenon; it is early-magnitude with the 5% late tail folded in.

Do not replace the champion with `is_early`. If we ever want a learnable promise-related output, it is **signed days early / better ETA**, told as padding-aware duration, with horizon either in X (we are scoring the quote) or out of X (we are scoring transit time only).

Reproduce:

```bash
uv run python scripts/experiment_early_delta.py
```
