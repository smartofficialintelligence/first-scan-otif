# Milestone 10 — Airflow triggers

Local-first orchestration. Cloud Composer is optional and **must not** stay always-on ([COST.md](../COST.md)).

## DAGs

| File | DAG id | Purpose |
|------|--------|---------|
| `airflow/dags/olist_replay_dag.py` | `olist_replay_canary` | Replay holdout → `artifacts/prediction_logs.jsonl` |
| `airflow/dags/olist_release_labels_dag.py` | `olist_release_labels` | `label_released` where `virtual_now >= prediction_ts + 7d` |
| `airflow/dags/olist_evaluate_delayed_dag.py` | `olist_evaluate_delayed` | PR-AUC / Brier on **released** labels; quality alarm `> 0.03` drop |
| `airflow/dags/olist_drift_dag.py` | `olist_drift` | Per-feature PSI + high-band mix; writes `artifacts/drift_alarm.json` |
| `airflow/dags/olist_retrain_dag.py` | `olist_retrain` | **H5-gated** train → `REGISTERED_CANDIDATE`. Composer schedule `0 0 1 * *` (monthly) still requires H5. `reason=drift` also requires an active alarm. |
| `airflow/dags/olist_train_dag.py` | `olist_train` | Unconstrained M4 demo trigger (`make airflow-train-local`). Does **not** replace `olist_retrain`. |
| `airflow/dags/olist_decision_eval_dag.py` | `olist_daily_decision_evaluation` | Ledger business-sim rollup (action mix, late→on-time, spend; not model quality). |

Airflow DAG objects are defined when `airflow` is installed; otherwise `dag = None` and the files remain CLI entrypoints.

## Local (no Composer)

```bash
make replay-baseline          # or: uv run python airflow/dags/olist_replay_dag.py
make release-labels           # VIRTUAL_NOW=... to override demo clock
make evaluate-delayed
make drift-geo                # baseline log + drift_geo + PSI check
make approve-h5
make retrain-trigger          # fails without H5 / without alarm when reason=drift
make airflow-train-local      # M4 demo; skips H5 on purpose
```

Chain the contract:

```text
replay_canary → release_labels → evaluate_delayed
replay_canary (baseline + drift_*) → drift_check → H5 → retrain_trigger
```

Nothing auto-promotes. Retrain stops at **REGISTERED_CANDIDATE**.

## Human gates (still required)

| Gate | When |
|------|------|
| **H5** | File `artifacts/h5_retrain_approval.json` (`make approve-h5`) before `olist_retrain` |
| **H6** | Before promoting a registered candidate to champion |
| **H4** | Before changing canary traffic after delayed-label gates |

Alarms open a flag only. `olist_train` must not be used as the production retrain path.

## Composer note

If demonstrating managed Airflow, create Composer only for the demo window and tear it down with `make demo-down`. Prefer these local DAG entrypoints for day-to-day work. Monthly cron on `olist_retrain` is the intended Composer schedule; the task still fails closed without H5.
