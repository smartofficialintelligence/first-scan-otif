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
if not PROJECT:
    # feast apply loads this module; require the project from env (no hardcoded id).
    raise RuntimeError("Set GCP_PROJECT_ID before feast apply / materialize")

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
