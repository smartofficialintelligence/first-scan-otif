#!/usr/bin/env python3
"""Create an intentionally degraded challenger artifact for bad-canary demos."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from olist_ml.canary.degraded import DegradedProbabilityModel
from olist_ml.logging import get_logger, setup_logging
from olist_ml.training.package import ModelMeta, load_artifact, save_artifact

logger = get_logger(__name__)


def create_bad_challenger(
    *,
    source_model: Path = Path("artifacts/model.joblib"),
    source_meta: Path = Path("artifacts/model_meta.json"),
    out_model: Path = Path("artifacts/model_challenger_bad.joblib"),
    out_meta: Path = Path("artifacts/model_challenger_bad_meta.json"),
    mode: str = "invert",
    noise_scale: float = 0.35,
    seed: int = 42,
) -> ModelMeta:
    setup_logging()
    if not source_model.exists() or not source_meta.exists():
        raise SystemExit(f"Source artifact missing: {source_model} / {source_meta}")

    base, meta = load_artifact(source_model, source_meta)
    degraded = DegradedProbabilityModel(base, mode=mode, noise_scale=noise_scale, seed=seed)
    bad_version = f"{meta.model_version}-bad"
    bad_meta = ModelMeta(
        model_version=bad_version,
        trained_at=meta.trained_at,
        feature_names=list(meta.feature_names),
        best_params=dict(meta.best_params),
        metrics={
            **{k: float(v) for k, v in meta.metrics.items() if isinstance(v, (int, float))},
            "intentionally_degraded": 1.0,
        },
        git_sha=meta.git_sha,
        snapshot_id=meta.snapshot_id,
        n_train=meta.n_train,
        n_valid=meta.n_valid,
        n_test=meta.n_test,
    )

    out_model.parent.mkdir(parents=True, exist_ok=True)
    save_artifact(degraded, bad_meta, model_path=out_model, meta_path=out_meta)
    note = {
        "degrade_mode": mode,
        "noise_scale": noise_scale,
        "seed": seed,
        "source_model_version": meta.model_version,
        "challenger_model_version": bad_version,
    }
    note_path = out_meta.with_name(out_meta.stem + "_note.json")
    note_path.write_text(json.dumps(note, indent=2), encoding="utf-8")
    logger.info("Wrote bad challenger %s (%s)", out_model, bad_version)
    return bad_meta


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Create degraded challenger model artifact")
    parser.add_argument("--source-model", type=Path, default=Path("artifacts/model.joblib"))
    parser.add_argument("--source-meta", type=Path, default=Path("artifacts/model_meta.json"))
    parser.add_argument("--out-model", type=Path, default=Path("artifacts/model_challenger_bad.joblib"))
    parser.add_argument(
        "--out-meta", type=Path, default=Path("artifacts/model_challenger_bad_meta.json")
    )
    parser.add_argument(
        "--mode",
        choices=("invert", "swap", "noise"),
        default="invert",
        help="How to degrade calibrated probabilities",
    )
    parser.add_argument("--noise-scale", type=float, default=0.35)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args(argv)
    create_bad_challenger(
        source_model=args.source_model,
        source_meta=args.source_meta,
        out_model=args.out_model,
        out_meta=args.out_meta,
        mode=args.mode,
        noise_scale=args.noise_scale,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
