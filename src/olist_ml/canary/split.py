"""Champion / challenger traffic attribution (locked 90/10)."""

from __future__ import annotations

import hashlib


def traffic_bucket_for_order(order_id: str) -> str:
    """
    Deterministic 90/10 attribution.

    hash(order_id) % 10 == 0 → challenger (10%); else champion (90%).
    Uses a stable digest so attribution does not depend on Python's randomized hash().
    """
    digest = hashlib.sha256(order_id.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 10
    return "challenger" if bucket == 0 else "champion"
