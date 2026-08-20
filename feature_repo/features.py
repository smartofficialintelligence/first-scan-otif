"""Feast feature views and services.

Offline source: BigQuery mart `ml.fct_seller_features` (dbt).
Online store: SQLite for demo-off; Memorystore Redis is demo-on only (later).
"""

from __future__ import annotations

import os
from datetime import timedelta

from feast import BigQuerySource, FeatureService, FeatureView, Field
from feast.types import Float64, UnixTimestamp

from entities import seller

PROJECT = os.environ.get("GCP_PROJECT_ID", "").strip()
# `feast apply` / `materialize` resolve a real table and still require the env
# var (checked in scripts/feast_apply_materialize.py). Importing this module
# without it — tooling, tests, a serving container inspecting definitions —
# yields a placeholder table name instead of raising, so an unset project can
# never take down the serving process.
PROJECT_IS_PLACEHOLDER = not PROJECT
if PROJECT_IS_PLACEHOLDER:
    PROJECT = "unset-project"

seller_features_source = BigQuerySource(
    name="seller_features_bq",
    table=f"{PROJECT}.ml.fct_seller_features",
    timestamp_field="event_timestamp",
)

# Freshness SLA default 36h (docs/features.md / Settings.feature_freshness_sla_hours).
seller_liveness_v1 = FeatureView(
    name="seller_liveness_v1",
    entities=[seller],
    ttl=timedelta(hours=36),
    schema=[
        Field(name="feature_timestamp", dtype=UnixTimestamp),
        Field(name="seller_order_count_7d", dtype=Float64),
        Field(name="seller_order_count_30d", dtype=Float64),
        Field(name="seller_order_count_90d", dtype=Float64),
        Field(name="seller_late_rate_7d", dtype=Float64),
        Field(name="seller_late_rate_30d", dtype=Float64),
        Field(name="seller_late_rate_90d", dtype=Float64),
    ],
    source=seller_features_source,
    online=True,
    description=(
        "PIT seller rolling order counts and late rates (7/30/90d). "
        "Missing entity → caller applies documented defaults."
    ),
)

seller_online_v1 = FeatureService(
    name="seller_online_v1",
    features=[seller_liveness_v1],
    description="Online seller historical features for serving (demo-on path).",
)
