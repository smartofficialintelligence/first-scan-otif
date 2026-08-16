"""Feature name contracts shared by training and serving."""

from __future__ import annotations

from typing import Final

# Numeric model matrix columns (order matters for inference).
NUMERIC_FEATURES: Final[list[str]] = [
    "purchase_hour",
    "purchase_dow",
    "purchase_month",
    "is_weekend",
    "item_count",
    "basket_value",
    "freight_value",
    "freight_to_basket_ratio",
    "seller_count",
    "category_count",
    "installment_count",
    "estimated_delivery_horizon_days",
    "approval_lag_hours",
    "geo_distance_km",
    "same_state",
    "avg_product_weight_g",
    "seller_order_count_7d",
    "seller_order_count_30d",
    "seller_order_count_90d",
    "seller_late_rate_7d",
    "seller_late_rate_30d",
    "seller_late_rate_90d",
    "seller_avg_freight_30d",
    "seller_avg_freight_90d",
    "seller_avg_basket_30d",
    "seller_avg_basket_90d",
    "customer_order_count_30d",
    "customer_order_count_90d",
    "customer_late_rate_90d",
    "category_late_rate_30d",
    "category_late_rate_90d",
    "category_order_count_90d",
]

CATEGORICAL_FEATURES: Final[list[str]] = [
    "payment_type_primary",
    "customer_state",
    "seller_state_primary",
    "primary_category",
]

FEATURE_COLUMNS: Final[list[str]] = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# Historical seller features that Feast serves online (v1 subset).
ONLINE_SELLER_FEATURES: Final[list[str]] = [
    "seller_order_count_7d",
    "seller_order_count_30d",
    "seller_order_count_90d",
    "seller_late_rate_7d",
    "seller_late_rate_30d",
    "seller_late_rate_90d",
]

BLOCKED_SOURCE_COLUMNS: Final[list[str]] = [
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "review_score",
    "review_creation_date",
    "review_answer_timestamp",
]
