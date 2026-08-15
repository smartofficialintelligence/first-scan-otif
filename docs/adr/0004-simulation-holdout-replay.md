# ADR 0004: Simulation via Olist holdout replay

## Status

Accepted — 2026-08-15

## Context

There is no organic production traffic. Canary, rollback, drift, and delayed-label monitoring still need to be demonstrated honestly.

## Decision

- Use chronological **`replay_holdout`** from real Olist orders.  
- Drive traffic with deterministic `scripts/replay_traffic.py`.  
- Simulate label delay with a virtual clock / `label_release_at`.  
- Provide named scenarios: `baseline`, `drift_seller_late`, `drift_geo`, `bad_canary`.  
- Never auto-promote on script success — human gates remain.

Full contract: [../simulation.md](../simulation.md).

## Consequences

- Holdout orders are sacred — never train on them.  
- Feast online demos need seller entities present for holdout sellers.  
- CI can test determinism and gate failure without full GCP.
