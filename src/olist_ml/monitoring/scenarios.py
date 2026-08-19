"""Named replay drift scenarios from docs/simulation.md."""

from __future__ import annotations

import numpy as np
import pandas as pd

from olist_ml.features.contracts import ONLINE_SELLER_FEATURES

DRIFT_FRACTION = 0.30
SELLER_LATE_MULTIPLIER = 1.5
GEO_INFLATE = 1.50
SELLER_LATE_COLUMNS = [c for c in ONLINE_SELLER_FEATURES if "late_rate" in c]


def apply_drift_scenario(
    frame: pd.DataFrame,
    scenario: str,
    *,
    seed: int = 42,
    fraction: float = DRIFT_FRACTION,
) -> pd.DataFrame:
    """
    Mutate a copy of the holdout for a named scenario.

    ``baseline`` / ``bad_canary``: no feature shift.
    ``drift_seller_late``: multiply seller_late_rate_* by 1.5 (cap 1.0) on ``fraction`` of rows.
    ``drift_geo``: inflate geo_distance_km by +50% on ``fraction`` of rows.
    """
    out = frame.copy()
    name = (scenario or "baseline").strip().lower()
    if name in {"baseline", "bad_canary", ""}:
        return out
    if out.empty:
        return out
    rng = np.random.default_rng(seed)
    n = len(out)
    n_shift = max(1, int(round(n * fraction)))
    idx = rng.choice(out.index.to_numpy(), size=min(n_shift, n), replace=False)
    if name == "drift_seller_late":
        for col in SELLER_LATE_COLUMNS:
            if col not in out.columns:
                continue
            vals = pd.to_numeric(out.loc[idx, col], errors="coerce").fillna(0.0)
            out.loc[idx, col] = (vals * SELLER_LATE_MULTIPLIER).clip(upper=1.0)
        return out
    if name == "drift_geo":
        if "geo_distance_km" in out.columns:
            vals = pd.to_numeric(out.loc[idx, "geo_distance_km"], errors="coerce").fillna(0.0)
            out.loc[idx, "geo_distance_km"] = vals * GEO_INFLATE
        return out
    raise ValueError(f"Unknown replay scenario: {scenario}")
