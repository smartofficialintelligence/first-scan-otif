"""Population Stability Index and related distribution-shift helpers."""

from __future__ import annotations

import numpy as np

PSI_ALARM_THRESHOLD = 0.2
HIGH_BAND_RELATIVE_SHIFT_THRESHOLD = 0.20


def population_stability_index(
    expected: np.ndarray,
    actual: np.ndarray,
    bins: int = 10,
) -> float:
    """PSI between two 1-d samples. Falls back to |Δμ|/σ when bins collapse."""
    expected = np.asarray(expected, dtype=float)
    actual = np.asarray(actual, dtype=float)
    expected = expected[np.isfinite(expected)]
    actual = actual[np.isfinite(actual)]
    if len(expected) < 2 or len(actual) < 2:
        return 0.0
    quantiles = np.linspace(0, 1, bins + 1)
    cuts = np.unique(np.quantile(expected, quantiles))
    if len(cuts) < 3:
        mu_e, mu_a = float(np.mean(expected)), float(np.mean(actual))
        sigma = float(np.std(expected)) or 1.0
        return abs(mu_a - mu_e) / sigma
    # Dedicated overflow bins: mass shifted outside the baseline range must
    # register as drift, not silently drop out of the histogram (which would
    # renormalize the remainder and attenuate PSI for exactly the shifts this
    # check exists to catch). The upper overflow starts strictly above the
    # baseline max so baseline mass at the max stays in the top regular bin.
    upper = np.nextafter(cuts[-1], np.inf)
    edges = np.concatenate([[-np.inf], cuts[:-1].astype(float), [upper], [np.inf]])
    exp_counts, _ = np.histogram(expected, bins=edges)
    act_counts, _ = np.histogram(actual, bins=edges)
    exp_pct = exp_counts / max(int(exp_counts.sum()), 1)
    act_pct = act_counts / max(int(act_counts.sum()), 1)
    exp_pct = np.clip(exp_pct, 1e-6, None)
    act_pct = np.clip(act_pct, 1e-6, None)
    return float(np.sum((act_pct - exp_pct) * np.log(act_pct / exp_pct)))


def high_band_relative_shift(baseline_high_rate: float, recent_high_rate: float) -> float:
    """|(recent - baseline)| / max(baseline, eps). 0.20 = 20% relative."""
    denom = max(abs(float(baseline_high_rate)), 1e-6)
    return abs(float(recent_high_rate) - float(baseline_high_rate)) / denom
