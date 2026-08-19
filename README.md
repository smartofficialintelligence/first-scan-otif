# First-scan OTIF scoring

Seller work is done at the first carrier scan. The remaining question is
whether the package will still miss the date already promised the
customer — and whether that order belongs in an exception queue.

This repo scores that miss, maps the score to a frozen P0–P3 policy, and
serves the same model. An agent can **copy** the action; it cannot pick a
cheaper one. Simulated dollars are a sensitivity check, not causal ROI.

Olist public e-commerce data. Portfolio artifact, not a live carrier.

## Held-out test (miss rate 4.6%)

Among later orders, ranking into a small queue beats drawing at random:

| Queue by score | Precision | Lift vs 4.6% |
| --- | ---: | ---: |
| Top 2.5% | **41.6%** | **9×** |
| Top 10% | **22.2%** | **4.8×** |

PR-AUC **0.296** · ROC-AUC **0.816** · Brier **0.038** · ECE **0.019**.
P1 / P2 cutoffs are frozen validation scores (0.56 / 0.32), not live
percentiles.

## Policy

Clock first, then score: P0 already past the promise (notice), P1
exception queue, P2 watch, P3 no action. Rules are in
[`docs/handoff-policy.md`](docs/handoff-policy.md).

Walkthrough: [`ARCHITECTURE.md`](ARCHITECTURE.md). Business write-up:
[`docs/business_assessment.md`](docs/business_assessment.md).

## What you can actually run

Same scorer locally or on Cloud Run (`/v1/predict`, Tree SHAP on
`/v1/explain`). Replay a bad canary, watch ready fail, promote the last
good artifact. Tear the stack down when you are done.

```bash
make setup && make data
make serve-local
make gcp-up && make gcp-smoke && make gcp-down   # optional; IAM-gated
make canary-bad
```

Python 3.11+, `uv` recommended. `make test` / `make lint`.

Warehouse is BigQuery + dbt. Feast online in this demo is SQLite (Redis
skipped for cost). Vertex, Composer, and Memorystore stay off.

## Limits

Public Olist, not live carrier events. No production SLO. No real-money
loop. SHAP is tree-level; the probability you see is calibrated.

License: MIT. Data: [Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) terms.
