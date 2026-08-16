#!/usr/bin/env python3
"""Safely undeploy a Vertex AI endpoint (dry-run by default)."""

from __future__ import annotations

import argparse
import os
import sys


def _instructions(*, project: str | None, region: str | None, endpoint_id: str | None) -> str:
    project = project or os.environ.get("GCP_PROJECT_ID", "<PROJECT_ID>")
    region = region or os.environ.get("GCP_REGION", "us-central1")
    endpoint_id = endpoint_id or os.environ.get("VERTEX_ENDPOINT_ID", "<ENDPOINT_ID>")
    return "\n".join(
        [
            "Manual Vertex undeploy steps:",
            f"  1. gcloud ai endpoints list --project={project} --region={region}",
            f"  2. gcloud ai endpoints undeploy-model {endpoint_id} \\",
            "       --deployed-model-id=<DEPLOYED_MODEL_ID> \\",
            f"       --project={project} --region={region}",
            f"  3. Optionally: gcloud ai endpoints delete {endpoint_id} \\",
            f"       --project={project} --region={region}",
            "Or use google.cloud.aiplatform.Endpoint.undeploy_all() with Application Default Credentials.",
        ]
    )


def teardown(
    *,
    apply: bool,
    project: str | None,
    region: str | None,
    endpoint_id: str | None,
) -> int:
    project = project or os.environ.get("GCP_PROJECT_ID")
    region = region or os.environ.get("GCP_REGION", "us-central1")
    endpoint_id = endpoint_id or os.environ.get("VERTEX_ENDPOINT_ID")

    if not apply:
        print("[dry-run] Would undeploy Vertex endpoint (no changes made).")
        print(_instructions(project=project, region=region, endpoint_id=endpoint_id))
        return 0

    creds = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not creds and not os.environ.get("GOOGLE_CLOUD_PROJECT") and not project:
        print("ERROR: --apply requires GCP credentials / project.", file=sys.stderr)
        print(_instructions(project=project, region=region, endpoint_id=endpoint_id))
        return 1

    if not endpoint_id:
        print("ERROR: set --endpoint-id or VERTEX_ENDPOINT_ID for --apply.", file=sys.stderr)
        print(_instructions(project=project, region=region, endpoint_id=endpoint_id))
        return 1

    try:
        from google.cloud import aiplatform  # type: ignore[import-untyped]
    except ImportError:
        print("google-cloud-aiplatform not installed; cannot apply automatically.")
        print(_instructions(project=project, region=region, endpoint_id=endpoint_id))
        return 1

    print(f"Initializing aiplatform project={project} location={region}")
    aiplatform.init(project=project, location=region)
    endpoint = aiplatform.Endpoint(endpoint_name=endpoint_id)
    print(f"Undeploying all models from endpoint {endpoint_id} ...")
    endpoint.undeploy_all()
    print("Done.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Undeploy Vertex AI endpoint (safe by default).")
    parser.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Print intended actions without changing GCP (default: true).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually undeploy (requires GCP credentials and aiplatform).",
    )
    parser.add_argument("--project", default=None, help="GCP project id")
    parser.add_argument("--region", default=None, help="GCP region")
    parser.add_argument("--endpoint-id", default=None, help="Vertex endpoint resource id or name")
    args = parser.parse_args(argv)

    apply = bool(args.apply)
    if apply:
        # --apply overrides dry-run
        dry_run = False
    else:
        dry_run = bool(args.dry_run)

    return teardown(
        apply=not dry_run,
        project=args.project,
        region=args.region,
        endpoint_id=args.endpoint_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
