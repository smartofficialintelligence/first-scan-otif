# Milestone 3 setup (Feast)

## What this milestone adds

- dbt mart `ml.fct_seller_features` (seller entity rows for Feast)
- `feature_repo/` Feast definitions: entity `seller`, view `seller_liveness_v1`, service `seller_online_v1`
  (named `feature_repo` so it does not shadow the `feast` Python package)
- Offline store: BigQuery (`ml.fct_seller_features`)
- Online store: **SQLite** under `data/feast/` (this demo). A production multi-replica API would typically use Redis so every instance shares one online store. We stayed on SQLite to avoid Memorystore idle cost.
- Scripts: apply+materialize, historical retrieval, offline/online parity
- Python adapter: `olist_ml.features.feast_client.FeastSellerClient` (lookup + freshness/stale)

Do not stand up Memorystore Redis for this artifact unless you are explicitly demoing a shared online store — then tear it down the same day.

## Prerequisites

1. Milestone 2 applied (BQ datasets + fixture ingest + dbt build)
2. Cursor secrets: `GCP_PROJECT_ID`, `GOOGLE_APPLICATION_CREDENTIALS_JSON`
3. `uv sync --all-extras` (installs `feast[gcp]`)

## Commands

```bash
source <(bash scripts/materialize_gcp_creds.sh)
cp dbt/profiles.yml.example dbt/profiles.yml
make dbt-build          # includes fct_seller_features
make feast-apply        # feast apply + materialize -> data/feast/
make feast-historical   # get_historical_features sample -> artifacts/
make feast-parity       # offline BQ latest vs online SQLite
# (scripts default --repo feature_repo)
```

## Accept criteria

| Check | How |
|---|---|
| Entity lookup works | `FeastSellerClient.get_online_features([...])` / `make feast-parity` |
| Freshness visible | `SellerFeatureRow.feature_timestamp` + `stale` (SLA default 36h) |
| Offline/online parity | `make feast-parity` within tolerance |
