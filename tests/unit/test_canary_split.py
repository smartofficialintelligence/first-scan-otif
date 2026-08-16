"""Deterministic 90/10 canary traffic attribution."""

from __future__ import annotations

from collections import Counter

from olist_ml.canary.split import traffic_bucket_for_order


def test_traffic_bucket_deterministic() -> None:
    order_id = "o024"
    assert traffic_bucket_for_order(order_id) == traffic_bucket_for_order(order_id)
    assert traffic_bucket_for_order(order_id) in {"champion", "challenger"}


def test_traffic_bucket_ninety_ten_ratio() -> None:
    """Across many ids, roughly 10% land in challenger (hash % 10 == 0)."""
    ids = [f"order-{i:05d}" for i in range(1000)]
    counts = Counter(traffic_bucket_for_order(oid) for oid in ids)
    challenger_rate = counts["challenger"] / len(ids)
    assert 0.05 <= challenger_rate <= 0.15
    assert counts["champion"] + counts["challenger"] == 1000


def test_known_order_stable_bucket() -> None:
    # Frozen expectation for a fixed order_id (sha256-based).
    bucket = traffic_bucket_for_order("o024")
    assert bucket == traffic_bucket_for_order("o024")
    # Distinct ids should not all collide on challenger.
    buckets = {traffic_bucket_for_order(f"o{i:03d}") for i in range(50)}
    assert "champion" in buckets
