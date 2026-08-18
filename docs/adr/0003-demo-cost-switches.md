# ADR 0003: Demo cost switches (near-zero idle)

## Status

Accepted — 2026-08-15

## Context

Managed ML demos fail budgets when endpoints, Redis, and Composer stay up. BigQuery storage for Olist is negligible; query cost is zero when idle. The operator needs an explicit off switch.

## Decision

1. Canonical data at rest lives in **GCS** (and local cache).  
2. **`make demo-up` / `make demo-down`** are first-class interfaces.  
3. `demo-down` must undeploy/delete: Vertex Endpoint, Memorystore, Composer (if any), and stop billable Cloud Run capacity.  
4. Prefer **deleting BQ demo datasets** on down; restore via load + dbt on up.  
5. Do **not** redesign around BigQuery external tables solely for cost — optional later, not required.

## Consequences

- Demo restore time is nonzero (load + dbt + Feast materialize).  
- Interview demos must be scheduled (warm-up scripted in RUNBOOK).  
- COST.md actuals required after first paid run.

## Amendment (2026-08-18)

Live serving on/off is **`make gcp-up` / `make gcp-down`**: Cloud Run + Monitoring only. Redis / Memorystore is **not** created. Vertex Endpoint stays behind `enable_vertex_endpoint=false`. `demo-up` / `demo-down` remain the **local** API switch.
