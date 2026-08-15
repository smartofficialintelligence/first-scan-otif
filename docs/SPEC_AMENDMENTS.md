# Spec amendment note

The uploaded draft **Cursor spec v0.2** remains useful for intent, acceptance criteria, testing strategy, and demo narrative.

**Superseded by this repo (2026-08-15):**

| v0.2 choice | Current locked choice |
|---|---|
| Vertex Feature Store | Feast |
| Vertex Experiments | MLflow |
| Vertex Model Registry | MLflow Model Registry |
| Implicit Vertex-centric orchestration | Airflow + Vertex Pipelines (train only) |
| “Do not add Airflow” | Airflow required for cross-system triggers |
| BigQuery always-on assumption | GCS canonical + BQ load on demo-up |

Authoritative docs:

- [LOCKED_DECISIONS.md](LOCKED_DECISIONS.md)
- [../ARCHITECTURE.md](../ARCHITECTURE.md)
- [simulation.md](simulation.md)
- [milestones.md](milestones.md)
- ADRs in [adr/](adr/)
