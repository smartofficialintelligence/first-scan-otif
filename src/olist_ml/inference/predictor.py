"""Shared prediction service used by REST and MCP."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from olist_ml.config import Settings
from olist_ml.features.assembler import frame_from_requests, select_feature_frame
from olist_ml.logging import get_logger
from olist_ml.monitoring.metrics import get_metrics
from olist_ml.schemas import (
    ExplainRequest,
    ExplainResponse,
    ModelInfoResponse,
    PredictRequest,
    PredictResponse,
    ReadyResponse,
    TopFeatureContribution,
)
from olist_ml.training.package import ModelMeta, load_artifact

logger = get_logger(__name__)

# Deterministic stub; SHAP is available but skipped by default to keep latency/deps light.
EXPLAIN_TIMEOUT_NOTE = (
    "Deterministic stub explanation (feature names with zero contributions). "
    "Full SHAP is available but skipped by default to avoid heavy compute/timeouts in tests."
)


def risk_band(probability: float, *, low_max: float, medium_max: float) -> str:
    if probability < low_max:
        return "low"
    if probability < medium_max:
        return "medium"
    return "high"


class PredictionService:
    """Single inference abstraction — no duplicated business logic in API layers."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model: Any | None = None
        self._meta: ModelMeta | None = None

    @property
    def ready(self) -> bool:
        return self._model is not None and self._meta is not None

    def load(self, model_path: Path | None = None, meta_path: Path | None = None) -> None:
        model_path = model_path or self.settings.model_path
        meta_path = meta_path or self.settings.model_meta_path
        if not model_path.exists() or not meta_path.exists():
            logger.warning("Model artifact missing at %s", model_path)
            self._model = None
            self._meta = None
            return
        self._model, self._meta = load_artifact(model_path, meta_path)
        logger.info("Loaded model_version=%s", self._meta.model_version)

    def readiness(self) -> ReadyResponse:
        if not self.ready:
            return ReadyResponse(ready=False, detail="model artifact not loaded")
        assert self._meta is not None
        return ReadyResponse(ready=True, model_version=self._meta.model_version)

    def model_info(self) -> ModelInfoResponse:
        if not self.ready or self._meta is None:
            return ModelInfoResponse(model_version="none", ready=False, feature_names=[])
        return ModelInfoResponse(
            model_version=self._meta.model_version,
            ready=True,
            feature_names=self._meta.feature_names,
            trained_at=self._meta.trained_at,
            metrics=self._meta.metrics,
        )

    def predict_one(
        self,
        request: PredictRequest,
        *,
        stale_features: bool = False,
        _record_metrics: bool = True,
    ) -> PredictResponse:
        started = time.perf_counter()
        band: str | None = None
        err = False
        try:
            if not self.ready or self._model is None or self._meta is None:
                raise RuntimeError("Model not ready")

            frame = frame_from_requests([request])
            X = select_feature_frame(frame)
            proba = float(self._model.predict_proba(X)[0, 1])
            proba = float(np.clip(proba, 0.0, 1.0))
            pred_ts = request.prediction_timestamp or request.purchase_timestamp
            if pred_ts.tzinfo is None:
                pred_ts = pred_ts.replace(tzinfo=UTC)
            band = risk_band(
                proba,
                low_max=self.settings.risk_low_max,
                medium_max=self.settings.risk_medium_max,
            )
            return PredictResponse(
                order_id=request.order_id,
                long_delivery_probability=proba,
                risk_band=band,  # type: ignore[arg-type]
                model_version=self._meta.model_version,
                prediction_timestamp=pred_ts,
                feature_timestamp=datetime.now(UTC),
            )
        except Exception:
            err = True
            raise
        finally:
            if _record_metrics:
                latency_ms = (time.perf_counter() - started) * 1000.0
                get_metrics().observe_predict(
                    latency_ms=latency_ms,
                    risk_band=band,
                    error=err,
                    stale=stale_features,
                )

    def explain_one(self, request: ExplainRequest | PredictRequest) -> ExplainResponse:
        """Return a deterministic stub explanation (feature names + zero contributions)."""
        started = time.perf_counter()
        err = False
        band: str | None = None
        try:
            if isinstance(request, ExplainRequest):
                predict_req = PredictRequest.model_validate(request.model_dump())
            else:
                predict_req = request
            # Avoid double-counting: predict_one records once; explain adds its own latency row.
            prediction = self.predict_one(predict_req, _record_metrics=False)
            band = prediction.risk_band
            assert self._meta is not None
            top_features = [
                TopFeatureContribution(feature=name, contribution=0.0)
                for name in self._meta.feature_names[:10]
            ]
            return ExplainResponse(
                order_id=prediction.order_id,
                model_version=prediction.model_version,
                long_delivery_probability=prediction.long_delivery_probability,
                top_features=top_features,
                method="stub",
                note=EXPLAIN_TIMEOUT_NOTE,
            )
        except Exception:
            err = True
            raise
        finally:
            latency_ms = (time.perf_counter() - started) * 1000.0
            get_metrics().observe_predict(
                latency_ms=latency_ms,
                risk_band=band,
                error=err,
                stale=False,
            )
