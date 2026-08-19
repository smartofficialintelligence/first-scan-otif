# Demo script

Locked sequence for interview / portfolio recording. Prefer local commands first; GCP apply needs a reviewed plan and secrets.

System walkthrough (read before the live demo): [ARCHITECTURE.md](../ARCHITECTURE.md).

**Product language:** promise-miss at **first carrier scan** → `promise_miss_probability` ([ADR 0006](adr/0006-handoff-promise-miss-noc.md)).  
Policy is deterministic **P0–P3** (notice / remaining-leg upgrade proxy / no action). The LangGraph agent **copies** that action — it does not re-choose policy.  
Do **not** claim causal ROI from intervention simulation — economics are versioned **simulation** assumptions (`allow_causal_roi_claims: false`). See [limitations-assumptions-proxies.md](limitations-assumptions-proxies.md).

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

Talking point: clocks at scan (`handling_days`, `remaining_to_promise_days`, `limit_miss`) plus approval-time basket/geo/seller history. Raw customer delivery never in X.

## Demo 2 — Train

```bash
make train-pipeline
# or: make airflow-train-local
# Show artifacts/mlruns + REGISTERED_CANDIDATE (not champion)
# ModelMeta persists p1_score_threshold / p2_score_threshold from validation scores
```

## Demo 3 — Serve

Local:

```bash
curl -s localhost:8080/health
curl -s localhost:8080/ready
curl -s localhost:8080/v1/model
# POST /v1/predict  |  POST /mcp (Streamable HTTP) → predict_promise_miss
# Response includes model_version + prediction_id + promise_miss_probability
```

Live Cloud Run (optional proof; tear down the same day):

```bash
make gcp-up && make gcp-smoke && make gcp-evidence && make gcp-down
```

Talking point: ranking quality is appendix. Lead with OTIF / exception queue / remaining-leg window. The live path is Cloud Run + baked champion, not Redis and not a Vertex Endpoint.

## Demo 4 — Canary

```bash
make replay-baseline
make release-labels
make evaluate-delayed
# Inspect artifacts/prediction_logs.jsonl — traffic_bucket + model_version + label_released
```

## Demo 5 — Rollback

```bash
make canary-bad
# create_bad_challenger → replay → release_labels → canary_decide
# Expect ROLLBACK → 100% champion recommendation (never auto-promote)
```

## Demo 6 — Drift / retrain

```bash
make drift-geo
cat artifacts/drift_alarm.json
make approve-h5
make retrain-trigger
# H6 required before promote. make airflow-train-local is the unconstrained M4 demo only.
```

## Demo 7 — Decision + agent layer (local)

Prediction → deterministic NOC bands → LangGraph executes the frozen action → simulated action → ledger.

```bash
# Offline harness (no API server; no LLM key):
make demo-decision
# → artifacts/demo_decision_chain.json  (scenarios B/C/D/E/G)
#    also appends simulated NOC actions to artifacts/decision_ledger.jsonl

make agent-evals
# → artifacts/agent_eval_report.json

make decision-eval
# → stdout headline + artifacts/decision_impact.md + decision_eval_report.json
#    (action mix, late→on-time, spend, delay-days; simulated $ only)
```

With API up (`make serve-local` / `make demo-up`):

```bash
# Predict
curl -s -X POST localhost:8080/v1/predict -H 'Content-Type: application/json' -d @- <<'EOF'
{"order_id":"demo-1","seller_id":"s1","purchase_timestamp":"2018-06-01T12:00:00Z",
 "item_count":2,"basket_value":180,"freight_value":20,"estimated_delivery_horizon_days":14,
 "remaining_to_promise_days":4,"geo_distance_km":250,"customer_state":"sp","seller_state_primary":"rj"}
EOF

# Deterministic NOC policy (same DecisionService as MCP recommend_policy_action)
curl -s -X POST localhost:8080/v1/decision -H 'Content-Type: application/json' -d @- <<'EOF'
{"order_id":"demo-1","seller_id":"s1","purchase_timestamp":"2018-06-01T12:00:00Z",
 "item_count":2,"basket_value":180,"freight_value":20,"estimated_delivery_horizon_days":14,
 "remaining_to_promise_days":4,"geo_distance_km":250,"customer_state":"sp","seller_state_primary":"rj",
 "simulate":false}
EOF

# Agent review (copies policy; human gate if upgrade_cost ≥ 20 or caller flags it)
curl -s -X POST localhost:8080/v1/agent/review -H 'Content-Type: application/json' -d @- <<'EOF'
{"order_id":"demo-1","prediction_id":"<from predict>","model_version":"<from predict>",
 "promise_miss_probability":0.81,"basket_value":300,"remaining_to_promise_days":4,
 "geo_distance_km":250,"same_state":0,"freight_value":20,
 "require_human_approval":true,"human_approved":true,"run_simulation":false}
EOF

curl -s localhost:8080/v1/metrics   # decision.* process counters + business_sim ledger rollup
curl -s localhost:8080/v1/policies/current
```

**Say out loud:**
1. Scan happens; model ranks promise-miss risk; **policy** maps remaining days + score band to one action.
2. Remaining-leg upgrade is a **freight-scaled demo proxy**, only when the remaining window and geography allow it. Otherwise notice.
3. Agent runs that frozen action (draft / tools / ledger). It does not re-argmax EV.
4. ActionExecutor is simulation-only — H12, no live carrier/customer side effects.
5. H9/H10 simulation defaults are approved (`econ-sim-v3`); still do **not** claim causal ROI (`make economics-gate`).
6. Optional LangSmith: set `LANGSMITH_API_KEY` — see [d9-langsmith.md](d9-langsmith.md).

MCP path (same services): `POST /mcp` on uvicorn/Cloud Run, or `make mcp-serve` (stdio) → `recommend_policy_action` / `execute_simulated_action`.

## Demo 8 — Cost / teardown

```bash
make demo-down
make gcp-down              # if you ran gcp-up
make teardown-endpoint     # dry-run unless --apply with live Vertex
# Fill COST.md actuals table after paid demo
```

**Never** skip human gates in the recorded story — show the approval step even if it is a CLI confirm.
