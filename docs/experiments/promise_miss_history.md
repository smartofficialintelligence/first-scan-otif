# Experiment: promise-miss history + route combos

Date: 2026-08-18  
Script: `scripts/experiment_promise_miss_history.py`  
Data: full Olist, production temporal split (`n_test=14,471`)  
Champion not changed.

## Question

If we retarget to **customer lateness** (`delivered > estimated`), does the obvious gap in the feature set save it?

That gap was: PIT rolling rates were defined on `long_delivery` (>14d), not on miss, and we had no **combo** miss rates (seller × customer_state, seller_state × customer_state). Also unused: `shipping_limit` tightness and seller **dispatch** miss history.

## Variants (all leakage-safe: no carrier/customer delivery in X)

| ID | X | y |
|---|---|---|
| A | Production features (late rates = >14d) | promise_miss |
| B | Replace late rates with **promise_miss** rates (seller/customer/category) | promise_miss |
| C | B + route combos (state×state, seller×dest state) | promise_miss |
| D | C + `shipping_limit_horizon_days` + seller limit-miss history + outcome-available seller miss rates | promise_miss |
| E | D without customer ETA horizon | promise_miss |
| F | Same X as D | **shipping_limit miss** |

Place-time PIT: prior `prediction_ts` only. `obs_*` rates also require prior `delivered < now`.

## Test results

Test promise-miss rate **4.8%**. Public honest bar on this dataset is ~**PR-AUC 0.33** ([samuelalex37](https://huggingface.co/samuelalex37/olist-delivery-risk-model)). Our old duration model on its own label was PR-AUC ~0.53 — that is **not** the comparison that matters.

| Variant | PR-AUC | ROC | Prec@10% | Lift@10% |
|---|---:|---:|---:|---:|
| A production duration-rates | 0.176 | 0.754 | 15.9% | 3.3× |
| B relabel history → miss | 0.199 | 0.766 | 19.7% | 4.1× |
| C + route combos | 0.194 | 0.761 | 19.5% | 4.1× |
| **D + limit / dispatch hist** | **0.217** | **0.785** | **19.9%** | 4.2× |
| E drop customer horizon | 0.150 | 0.685 | 14.7% | 3.1× |
| F target = limit_miss (base 7.9%) | 0.228 | 0.739 | 24.4% | 3.1× |

At 10% flag rate the best miss ranker is still **~80% false positives**. At 5% capacity, D reaches 27% precision (5.7× lift) — usable only if the action is cheap.

## What the idea got right

- Relabeling history **does** help: B beats A (~+0.02 PR-AUC). `seller_miss_rate_7d` is the strongest univariate miss feature (PR-AUC 0.117 vs 0.048 base) and the top gain feature in B.
- Route rates have univariate signal (`route_miss_rate_90d` = 0.110) and steal gain importance in C/D, but they **do not lift** the model over B. Customer state dummies already carried most of that.
- Dispatch/limit features add another ~+0.02 (B→D). Real, small.
- Outcome-available seller rates did not dominate; 7d place-time miss rate did.

## What it did not do

It does **not** get us to a demo-grade lateness model. Best miss PR-AUC **0.22** vs public honest ~0.33 vs the discarded duration chart at 0.53.

Dropping the customer horizon **hurts** miss ranking (E). Short promises are the ones that actually break; long promises are padded. Horizon is a legitimate checkout feature, but using it is “the ETA was aggressive,” not “we discovered hidden lateness.”

Seller **limit-miss** (F) is the cleaner SLO and is not easier: PR-AUC 0.23, prec@10% 24%. Same weak-signal shape.

## Decision

**Do not retarget the champion to promise-miss** on this feature recipe. The mechanical change is correct and we should keep the finding, but it does not change the product story: Olist customer lateness is a cheap-intervention ranker, not a 0.5 PR-AUC SLA model.

Reproduce:

```bash
uv run python scripts/experiment_promise_miss_history.py
```
