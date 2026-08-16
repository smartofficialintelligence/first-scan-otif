"""Feast entities for Olist late-delivery features."""

from feast import Entity
from feast.value_type import ValueType

seller = Entity(
    name="seller",
    join_keys=["seller_id"],
    value_type=ValueType.STRING,
    description="Olist seller; online historical rate/count features (v1).",
)
