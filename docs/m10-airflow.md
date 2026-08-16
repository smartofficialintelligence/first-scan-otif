# Milestone 10 — Airflow triggers

Local-first orchestration stubs. Cloud Composer is optional and **must not** stay always-on ([COST.md](../COST.md)).

## DAGs

| File | Purpose |
|------|---------|
| `airflow/dags/olist_train_dag.py` | Training trigger → `pipelines.local_pipeline` / `run_train_trigger()`. Airflow DAG when `airflow` is installed; else `dag = None`. |
| `airflow/dags/olist_drift_dag.py` | Drift stub: PSI / mean-shift on `proba` (or fixture numeric). Writes `artifacts/drift_alarm.json`. **Does not deploy.** |

## Local (no Composer)

```bash
make airflow-train-local
# equivalent:
uv run python airflow/dags/olist_train_dag.py --local

uv run python airflow/dags/olist_drift_dag.py
cat artifacts/drift_alarm.json
```

## Human gates (still required)

| Gate | When |
|------|------|
| **H5** | Before acting on a drift/performance alarm to start retrain |
| **H6** | Before promoting a registered candidate to champion |

Automation stops at **REGISTERED_CANDIDATE**. Alarms open a flag / ticket only — **no auto-promote**.

## Composer note

If demonstrating managed Airflow, create Composer only for the demo window and tear it down with `make demo-down`. Prefer these local DAG entrypoints for day-to-day work.
