# Demo script

Locked sequence for interview / portfolio recording. Prefer local commands first; GCP steps need H7 and secrets.

**Target language:** `long_delivery` (>14d from approval) → `long_delivery_probability` (ADR 0005).  
Do **not** claim causal ROI from intervention simulation — economics are approved **simulation** assumptions (H9/H10; `allow_causal_roi_claims: false`).

## Prep (day of)

1. Confirm prior `make demo-down`
2. `make sync && make fixtures && make test`
3. `make demo-up` (local uvicorn) → `make smoke-local`

## Demo 1 — Features

```bash
# dbt (needs GCP):
make ingest-fixtures-bq && make dbt-build
# Feast (needs GCP; SQLite online demo-off):
make feast-apply && make feast-historical
```

## Demo 2 — Train

```bash
make train-pipeline
# or: make airflow-train-local
# Show artifacts/mlruns + REGISTERED_CANDIDATE (not champion)
```

## Demo 3 — Serve

```bash
curl -s localhost:8080/health
curl -s localhost:8080/ready
curl -s localhost:8080/v1/model
# POST /v1/predict  |  make mcp-serve → predict_long_delivery
# Response includes model_version + prediction_id + long_delivery_probability
```

Talking point: test PR-AUC ~0.53, precision@10% ~65% (~3.2× lift vs 20% base rate) — see [business_assessment.md](business_assessment.md).

## Demo 4 — Canary

```bash
make replay-baseline
# Inspect artifacts/prediction_logs.jsonl — traffic_bucket + model_version
```

## Demo 5 — Rollback

```bash
make canary-bad
# create_bad_challenger → replay → canary_decide
# Expect ROLLBACK → 100% champion recommendation (never auto-promote)
```

## Demo 6 — Drift / retrain

```bash
make drift-check
cat artifacts/drift_alarm.json
# H5 → make airflow-train-local / train-pipeline → new candidate
# H6 required before promote
```

## Demo 7 — Decision + agent layer (local)

Prediction → deterministic EV policy → optional LangGraph agent review → simulated action → ledger.

```bash
# Offline harness (no API server; no LLM key):
make demo-decision
# → artifacts/demo_decision_chain.json  (scenarios B/C/D/E/G)

make agent-evals
# → artifacts/agent_eval_report.json

make decision-eval
# → artifacts/decision_eval_report.json  (ledger summary; simulated $ only)
```

With API up (`make serve-local` / `make demo-up`):

```bash
# Predict
curl -s -X POST localhost:8080/v1/predict -H 'Content-Type: application/json' -d @- <<'EOF'
{"order_id":"demo-1","seller_id":"s1","purchase_timestamp":"2018-06-01T12:00:00Z",
 "item_count":2,"basket_value":180,"freight_value":20,"estimated_delivery_horizon_days":14}
EOF

# Deterministic policy (same DecisionService as MCP recommend_policy_action)
curl -s -X POST localhost:8080/v1/decision -H 'Content-Type: application/json' -d @- <<'EOF'
{"order_id":"demo-1","seller_id":"s1","purchase_timestamp":"2018-06-01T12:00:00Z",
 "item_count":2,"basket_value":180,"freight_value":20,"estimated_delivery_horizon_days":14,
 "simulate":false}
EOF

# Agent review + human gate (approve)
curl -s -X POST localhost:8080/v1/agent/review -H 'Content-Type: application/json' -d @- <<'EOF'
{"order_id":"demo-1","prediction_id":"<from predict>","model_version":"<from predict>",
 "long_delivery_probability":0.81,"basket_value":300,
 "require_human_approval":true,"human_approved":true,"run_simulation":false}
EOF

curl -s localhost:8080/v1/metrics   # decision.agent_reviews, action_distribution
curl -s localhost:8080/v1/policies/current
```

**Say out loud:**
1. Model ranks long-delivery risk; policy chooses actions by expected value under **versioned simulation assumptions**.
2. Agent may only pick approved actions; near-ties prefer lower cost; high-value can require human approval.
3. ActionExecutor is simulation-only — not live seller/customer side effects.
4. H9/H10 simulation defaults are approved (`econ-sim-v2`); still do **not** claim causal ROI (`make economics-gate`).
5. Optional LangSmith: set `LANGSMITH_API_KEY` — see [d9-langsmith.md](d9-langsmith.md).

MCP path (same services): `make mcp-serve` → `recommend_policy_action` / `execute_simulated_action`.

## Demo 8 — Cost / teardown

```bash
make demo-down
make teardown-endpoint   # dry-run unless --apply with live Vertex
# Fill COST.md actuals table after paid demo
```

**Never** skip human gates in the recorded story — show the approval step even if it is a CLI confirm.
