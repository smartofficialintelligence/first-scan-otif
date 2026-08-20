"""Shared prediction service used by REST and MCP."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from olist_ml.config import Settings
from olist_ml.features.assembler import frame_from_requests, select_feature_frame
from olist_ml.features.contracts import ONLINE_SELLER_FEATURES
from olist_ml.features.feast_client import FeastSellerClient
from olist_ml.inference.explain import (
    SHAP_NOTE,
    STUB_NOTE,
    tree_shap_top_features,
    unwrap_xgb_classifier,
)
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
        self._shap_explainer: Any | None = None
        self.feast_client: FeastSellerClient | None = None
        self.last_feast_lookup_ms: float = 0.0
        if settings.feast_online_enabled:
            self.feast_client = FeastSellerClient(
                repo_path=settings.feast_repo_path,
                freshness_sla_hours=settings.feature_freshness_sla_hours,
            )

    def hydrate_request(self, request: PredictRequest) -> tuple[PredictRequest, bool]:
        """Fill omitted online seller features from Feast. Request values win.

        Does not invent history: Feast is queried only for None fields. Missing
        Feast entity stays None here; assembler applies cold-start 0 after.
        """
        self.last_feast_lookup_ms = 0.0
        if self.feast_client is None or not request.seller_id:
            return request, False
        needed = [name for name in ONLINE_SELLER_FEATURES if getattr(request, name) is None]
        if not needed:
            return request, False
        started = time.perf_counter()
        try:
            rows = self.feast_client.get_online_features([request.seller_id])
        except Exception:
            logger.exception("Feast online lookup failed for seller_id=%s", request.seller_id)
            self.last_feast_lookup_ms = (time.perf_counter() - started) * 1000.0
            return request, True
        self.last_feast_lookup_ms = (time.perf_counter() - started) * 1000.0
        if not rows:
            return request, True
        row = rows[0]
        updates = {
            name: row.features[name]
            for name in needed
            if name in row.features
        }
        filled = request.model_copy(update=updates)
        return filled, bool(row.stale)

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
            self._shap_explainer = None
            return
        self._model, self._meta = load_artifact(model_path, meta_path)
        self._shap_explainer = None
        logger.info("Loaded model_version=%s", self._meta.model_version)
        # Registry construction costs seconds; do it here (inside the startup
        # probe) rather than on the first scored request after a cold start.
        if self.feast_client is not None:
            self.feast_client.warm()

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
            target=self._meta.target,
            p1_score_threshold=self._meta.p1_score_threshold,
            p2_score_threshold=self._meta.p2_score_threshold,
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

            request, feast_stale = self.hydrate_request(request)
            stale_features = bool(stale_features or feast_stale)
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
                prediction_id=str(uuid.uuid4()),
                promise_miss_probability=proba,
                risk_band=band,  # type: ignore[arg-type]
                model_version=self._meta.model_version,
                prediction_timestamp=pred_ts,
                feature_timestamp=datetime.now(UTC),
                target=self._meta.target,
                p1_score_threshold=self._meta.p1_score_threshold,
                p2_score_threshold=self._meta.p2_score_threshold,
                stale_features=stale_features,
                feast_lookup_ms=self.last_feast_lookup_ms,
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
        """Score the request, then Tree-SHAP the XGBoost booster (pre-calibration)."""
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
            top_features, method, note = self._explain_features(predict_req)
            return ExplainResponse(
                order_id=prediction.order_id,
                model_version=prediction.model_version,
                promise_miss_probability=prediction.promise_miss_probability,
                top_features=top_features,
                method=method,  # type: ignore[arg-type]
                note=note,
                target=prediction.target,
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

    def _explain_features(
        self, request: PredictRequest
    ) -> tuple[list[TopFeatureContribution], str, str]:
        if self._model is None or self._meta is None:
            raise RuntimeError("Model not ready")
        bundle = self._model
        xgb_clf = unwrap_xgb_classifier(getattr(bundle, "model", bundle))
        preprocessor = getattr(bundle, "preprocessor", None)
        if xgb_clf is None or preprocessor is None:
            logger.warning("No XGBoost tree to explain; using stub")
            return self._stub_features(), "stub", STUB_NOTE
        try:
            frame = select_feature_frame(frame_from_requests([request]))
            xt = preprocessor.transform(frame)
            names = [str(n) for n in preprocessor.get_feature_names_out()]
            top, self._shap_explainer = tree_shap_top_features(
                xgb_clf,
                xt,
                names,
                explainer=self._shap_explainer,
            )
            return top, "shap", SHAP_NOTE
        except Exception:
            logger.exception("Tree SHAP failed; using stub")
            self._shap_explainer = None
            return self._stub_features(), "stub", STUB_NOTE

    def _stub_features(self) -> list[TopFeatureContribution]:
        assert self._meta is not None
        return [
            TopFeatureContribution(feature=name, contribution=0.0)
            for name in self._meta.feature_names[:10]
        ]
