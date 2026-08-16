# Feature / model iteration notes

Date: 2026-08-16  
Branch: `cursor/feature-model-iteration-642f`  
Model: `local-20260816T081113Z`

## Baseline (prior full Olist train)

- Test PR-AUC ≈ **0.096**, ROC-AUC ≈ 0.67, Brier ≈ 0.046
- Late rate overall ≈ 8.1%

## After iteration

| Split | n | Late rate | PR-AUC | ROC-AUC | Brier | ECE |
|---|---:|---:|---:|---:|---:|---:|
| Valid | 14,471 | 12.1% | 0.359 | 0.783 | 0.091 | ~0.000 |
| Test | 14,471 | 4.8% | **0.197** | 0.780 | 0.043 | 0.016 |

Changes that moved the needle: expanded PIT history features (seller/customer/category + order extras), temporal Optuna CV, early stopping, held-out isotonic calibration.

Reproduce:

```bash
uv run python -m olist_ml.training.pipeline --data-dir data/raw --trials 25
```
