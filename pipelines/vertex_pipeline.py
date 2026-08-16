"""
Vertex AI training pipeline stub (compile-or-skip without GCP).

CustomJob / pipeline entrypoint (locked for M4):

    python -m pipelines.local_pipeline --data-dir $DATA_DIR --trials $TRIALS

Environment (never hardcode project ids in source):

- GCP_PROJECT_ID
- GCP_REGION (e.g. us-central1)
- VERTEX_PIPELINE_ROOT (gs://… staging)
- MLFLOW_TRACKING_URI (file:./artifacts/mlruns or gs://… / remote server)

This module optionally compiles a minimal pipeline JSON/YAML description when
``google-cloud-aiplatform`` is installed. Without the SDK it prints a skip
message and exits 0 so local CI stays green.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PIPELINE_NAME = "olist-late-delivery-train"
CUSTOM_JOB_ENTRYPOINT = (
    "python -m pipelines.local_pipeline --data-dir ${DATA_DIR:-data/fixtures} --trials ${TRIALS:-3}"
)

STEP_GRAPH = [
    "validate_data",
    "tune",
    "train",
    "calibrate",
    "evaluate",
    "log_mlflow",
    "register_candidate",
]


def describe_pipeline() -> dict:
    """Return a portable description of the Vertex CustomJob wiring."""
    return {
        "display_name": PIPELINE_NAME,
        "entrypoint": CUSTOM_JOB_ENTRYPOINT,
        "steps": STEP_GRAPH,
        "lifecycle_terminal_state": "REGISTERED_CANDIDATE",
        "env_vars": [
            "GCP_PROJECT_ID",
            "GCP_REGION",
            "VERTEX_PIPELINE_ROOT",
            "MLFLOW_TRACKING_URI",
            "DATA_DIR",
            "TRIALS",
        ],
        "notes": (
            "Compile/submit only when google-cloud-aiplatform is available and "
            "GCP credentials are configured. Do not auto-promote past human gates."
        ),
    }


def compile_or_skip(output_path: Path | None = None) -> int:
    """
    If aiplatform is importable, write a compile stub artifact; else skip.

    Returns process exit code (0 on success or intentional skip).
    """
    desc = describe_pipeline()
    out = output_path or Path("artifacts/vertex_pipeline_stub.json")

    try:
        from google.cloud import aiplatform  # noqa: F401
    except ImportError:
        print(
            "google-cloud-aiplatform not installed — skipping Vertex compile. "
            f"Entrypoint remains: {CUSTOM_JOB_ENTRYPOINT}"
        )
        print(json.dumps(desc, indent=2))
        return 0

    # SDK present: write a JSON description usable as a CustomJob container command template.
    # Full KFP compile is deferred until container image + pipeline root are configured via env.
    project = os.environ.get("GCP_PROJECT_ID")
    region = os.environ.get("GCP_REGION", "us-central1")
    pipeline_root = os.environ.get("VERTEX_PIPELINE_ROOT")

    payload = {
        **desc,
        "project_env": "GCP_PROJECT_ID",
        "project_set": bool(project),
        "region": region,
        "pipeline_root_set": bool(pipeline_root),
        "compile_mode": "stub",
        "aiplatform_available": True,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"Wrote Vertex pipeline stub to {out}")
    if not project or not pipeline_root:
        print(
            "Note: set GCP_PROJECT_ID and VERTEX_PIPELINE_ROOT to submit a real CustomJob."
        )
    return 0


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Vertex pipeline compile-or-skip stub")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/vertex_pipeline_stub.json"),
        help="Where to write the stub JSON when the SDK is available",
    )
    args = parser.parse_args(argv)
    sys.exit(compile_or_skip(args.output))


if __name__ == "__main__":
    main()
