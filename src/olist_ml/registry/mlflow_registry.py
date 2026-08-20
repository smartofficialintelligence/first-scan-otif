"""MLflow tracking + candidate registration (file/GCS-friendly)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import mlflow
from mlflow.tracking import MlflowClient

from olist_ml.logging import get_logger
from olist_ml.training.package import ModelMeta

logger = get_logger(__name__)

MODEL_NAME = "olist-late-delivery"
# FileStore is unreliable on MLflow 3.x in this environment; prefer SQLite locally.
DEFAULT_TRACKING_URI = "sqlite:///./artifacts/mlflow.db"
LIFECYCLE_TRAINED = "TRAINED"
LIFECYCLE_EVALUATED = "EVALUATED"
LIFECYCLE_REGISTERED_CANDIDATE = "REGISTERED_CANDIDATE"


def default_tracking_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)


def _normalize_tracking_uri(tracking_uri: str) -> str:
    """Normalize local URIs to absolute paths for stable backends."""
    if tracking_uri.startswith("file:"):
        os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
        parsed = urlparse(tracking_uri)
        raw = parsed.path if parsed.path else tracking_uri.removeprefix("file:")
        path = Path(raw)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        path.mkdir(parents=True, exist_ok=True)
        return f"file://{path}"
    if tracking_uri.startswith("sqlite:"):
        # sqlite:///./rel.db or sqlite:////abs.db
        prefix = "sqlite:///"
        if not tracking_uri.startswith(prefix):
            return tracking_uri
        rest = tracking_uri[len(prefix) :]
        path = Path(rest)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{path}"
    return tracking_uri


def configure_tracking(tracking_uri: str | None = None) -> str:
    uri = _normalize_tracking_uri(tracking_uri or default_tracking_uri())
    mlflow.set_tracking_uri(uri)
    return uri


def start_run(
    *,
    run_name: str | None = None,
    tags: dict[str, str] | None = None,
    tracking_uri: str | None = None,
) -> mlflow.ActiveRun:
    configure_tracking(tracking_uri)
    run = mlflow.start_run(run_name=run_name)
    if tags:
        mlflow.set_tags(tags)
    return run


def log_params(params: dict[str, Any]) -> None:
    flat: dict[str, Any] = {}
    for k, v in params.items():
        flat[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
    if flat:
        mlflow.log_params(flat)


def log_metrics(metrics: dict[str, float]) -> None:
    numeric = {k: float(v) for k, v in metrics.items() if v is not None}
    if numeric:
        mlflow.log_metrics(numeric)


def log_artifact(path: Path | str, artifact_path: str | None = None) -> None:
    mlflow.log_artifact(str(path), artifact_path=artifact_path)


class JoblibCandidateModel(mlflow.pyfunc.PythonModel):
    """Load joblib ModelBundle (or any object with predict_proba) for MLflow serving."""

    def load_context(self, context):  # noqa: ANN001
        import joblib

        self.bundle = joblib.load(context.artifacts["model"])

    def predict(self, context, model_input):  # noqa: ANN001, ANN201
        import pandas as pd

        if not isinstance(model_input, pd.DataFrame):
            model_input = pd.DataFrame(model_input)
        return self.bundle.predict_proba(model_input)[:, 1]


def log_and_register_candidate(
    meta: ModelMeta,
    model_path: Path | str,
    meta_path: Path | str,
    *,
    tracking_uri: str | None = None,
    experiment_name: str = "olist-late-delivery",
) -> str:
    """Log metrics/artifacts and register model as REGISTERED_CANDIDATE. Returns run_id."""
    model_path = Path(model_path)
    meta_path = Path(meta_path)
    if not model_path.exists():
        raise FileNotFoundError(f"Model artifact missing: {model_path}")
    if not meta_path.exists():
        raise FileNotFoundError(f"Model meta missing: {meta_path}")

    uri = configure_tracking(tracking_uri)
    mlflow.set_experiment(experiment_name)

    with start_run(run_name=meta.model_version, tracking_uri=uri) as run:
        # git_sha / snapshot_id make a run auditable: which commit trained it and
        # whether the features came from the warehouse or the pandas builder.
        provenance = {
            "git_sha": meta.git_sha or "unknown",
            "snapshot_id": meta.snapshot_id or "unknown",
        }
        mlflow.set_tags(
            {
                "lifecycle_state": LIFECYCLE_TRAINED,
                "model_version": meta.model_version,
                **provenance,
            }
        )
        log_params({f"param_{k}": v for k, v in meta.best_params.items()})
        log_params(
            {
                "n_train": meta.n_train or 0,
                "n_valid": meta.n_valid or 0,
                "n_test": meta.n_test or 0,
            }
        )
        log_metrics(meta.metrics)
        mlflow.set_tag("lifecycle_state", LIFECYCLE_EVALUATED)

        log_artifact(model_path, artifact_path="candidate")
        log_artifact(meta_path, artifact_path="candidate")

        mlflow.pyfunc.log_model(
            artifact_path="model",
            python_model=JoblibCandidateModel(),
            artifacts={"model": str(model_path), "meta": str(meta_path)},
            registered_model_name=MODEL_NAME,
        )
        mlflow.set_tags(
            {
                "lifecycle_state": LIFECYCLE_REGISTERED_CANDIDATE,
                "model_version": meta.model_version,
                **provenance,
            }
        )
        run_id = run.info.run_id
        logger.info(
            "Registered candidate model=%s run_id=%s version=%s uri=%s",
            MODEL_NAME,
            run_id,
            meta.model_version,
            uri,
        )
        return run_id


def get_candidate_info(run_id: str, *, tracking_uri: str | None = None) -> dict[str, Any]:
    """Fetch tags/metrics/params for a registered candidate run."""
    configure_tracking(tracking_uri)
    client = MlflowClient()
    run = client.get_run(run_id)
    tags = dict(run.data.tags)
    return {
        "run_id": run_id,
        "lifecycle_state": tags.get("lifecycle_state"),
        "model_version": tags.get("model_version"),
        "metrics": dict(run.data.metrics),
        "params": dict(run.data.params),
        "tags": tags,
        "status": run.info.status,
        "artifact_uri": run.info.artifact_uri,
    }
