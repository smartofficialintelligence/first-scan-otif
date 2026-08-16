"""Intentionally degraded estimators for bad-canary demos."""

from __future__ import annotations

from typing import Any

import numpy as np


class DegradedProbabilityModel:
    """Wrap a sklearn-compatible estimator and degrade calibrated probabilities."""

    def __init__(
        self,
        base: Any,
        *,
        mode: str = "invert",
        noise_scale: float = 0.35,
        seed: int = 42,
    ) -> None:
        self.base = base
        self.mode = mode
        self.noise_scale = noise_scale
        self.seed = seed
        self._rng = np.random.default_rng(seed)

    def predict_proba(self, X: Any) -> np.ndarray:
        proba = np.asarray(self.base.predict_proba(X), dtype=float)
        out = proba.copy()
        p1 = out[:, 1]
        if self.mode == "invert":
            p1 = 1.0 - p1
        elif self.mode == "swap":
            p1 = np.where(p1 >= 0.5, 1.0 - p1, np.clip(1.0 - p1 + 0.15, 0.0, 1.0))
        elif self.mode == "noise":
            noise = self._rng.normal(0.0, self.noise_scale, size=p1.shape)
            p1 = np.clip(p1 + noise, 0.0, 1.0)
        else:
            raise ValueError(f"Unknown degrade mode: {self.mode}")
        out[:, 1] = p1
        out[:, 0] = 1.0 - p1
        return out

    def predict(self, X: Any) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)

    def __sklearn_is_fitted__(self) -> bool:
        return True
