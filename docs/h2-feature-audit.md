# H2 — Feature / leakage audit

**Status:** completed for portfolio v1 (2026-08-16)  
**Auditor:** portfolio code review (implementation vs `docs/features.md`)  
**Scope:** shipped feature contract in `olist_ml.features.contracts` + local/dbt builders

## Verdict

**Accept** the candidate feature set for this portfolio artifact, with residual notes below.  
Blocked non-features remain blocked (reviews, post-outcome timestamps, closed-right history).

## Checklist results

| Check | Result |
|---|---|
| Source tables documented | Pass — see feature tables in `docs/features.md` |
| Timestamp / PIT (`event_ts < prediction_ts`) | Pass by design — history builders use `prediction_ts` with left-closed windows |
| Window semantics 7/30/90d | Pass — contract columns match windows |
| Knowable at `prediction_ts` | Pass for request-native + historical aggregates; labels use delivery outcome only as target |
| Online vs offline | Pass — seller liveness online subset documented; category/customer offline in v1 |
| Shared contract train/serve | Pass — `FEATURE_COLUMNS` / request schema shared |
| Explicit non-features excluded | Pass — no review scores / delivery carrier outcomes as features |

## Residual risks (accepted for v1)

1. **`geo_distance_km`:** zip/centroid proxy; medium leakage only if future geo used — current path is static join.
2. **Seller late rates:** must exclude current order (PIT). Local rolling history and dbt marts are responsible; keep parity tests green when Feast is on.
3. **Cold-start sellers/customers:** defaults / missing handling — model must tolerate nulls (already in API path).
4. **Temporal regime shift:** test base rate differs from train; documented in business assessment — not a leakage bug.

## Sign-off

| Field | Value |
|---|---|
| Gate | H2 |
| Decision | approved for portfolio v1 |
| Causal / production enterprise claim | not asserted — portfolio demo scope |
| Next review | before any live Vertex champion promote (H3/H4) |
