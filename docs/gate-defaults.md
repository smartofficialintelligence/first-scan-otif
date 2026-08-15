# Initial gate defaults

Configurable values shipped as defaults — tune after first real metrics.  
Do not treat these as eternal business truth.

## Offline promotion (candidate vs champion)

A candidate may be marked `APPROVED_FOR_CANARY` only if all pass:

| Check | Default |
|---|---|
| Data contracts | pass |
| Serialization / schema | pass |
| Probabilities in `[0, 1]` | pass |
| Primary metric | PR-AUC ≥ champion − `0.01` (absolute) |
| Brier | ≤ champion + `0.02` |
| ECE | ≤ `0.08` or ≤ champion + `0.02` |
| Segment floor | no segment with support ≥ 200 drops PR-AUC by `> 0.05` vs champion |
| Latency smoke | p95 predict path ≤ `500ms` locally / ≤ `1200ms` on demo endpoint |

Fail → remain `EVALUATED` / rejected tag; no canary.

## Canary (online)

| Check | Default |
|---|---|
| Traffic | 90% champion / 10% challenger |
| Min replay events before decision | `500` (or full holdout if smaller) |
| Error rate | challenger ≤ champion + `1pp` and ≤ `2%` absolute |
| p95 latency | challenger ≤ champion × `1.25` |
| Delayed-label PR-AUC | ≥ champion − `0.02` when labels released |
| Auto-promote | **never** — H4 required |

## Drift / retrain alarms (H5 still required)

| Signal | Default alarm |
|---|---|
| Feature drift (PSI on key features) | PSI `> 0.2` on any online seller feature or `geo_distance_km` |
| Prediction drift | risk_band high-rate shifts `> 20%` relative over baseline window |
| Delayed-label PR-AUC | drop `> 0.03` vs rolling baseline |
| Schedule | monthly retrain DAG regardless of alarms |

Alarms create an Airflow ticket/flag for H5 — they do not deploy.

## Freshness

| Signal | Default |
|---|---|
| Seller online feature SLA | `36h` during demos |
| Stale policy | predict with fallback prior; increment `stale_feature_rate` |
