#!/usr/bin/env bash
# Tear down Cloud Run + Monitoring. Keeps Artifact Registry, BQ, GCS, IAM.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TFDIR="$ROOT/terraform/environments/dev"
KEY="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/sa-key.json}"

if [[ ! -f "$KEY" ]]; then
  echo "Missing GCP key at $KEY" >&2
  exit 1
fi
PROJECT="${GCP_PROJECT_ID:-}"
if [[ -z "$PROJECT" ]]; then
  PROJECT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['project_id'])" "$KEY")"
fi

export GOOGLE_APPLICATION_CREDENTIALS="$KEY"
gcloud auth activate-service-account --key-file="$KEY" --quiet
gcloud config set project "$PROJECT" --quiet

echo "==> terraform: disable Cloud Run + Monitoring (keep registry)"
terraform -chdir="$TFDIR" apply -input=false -auto-approve \
  -var="project_id=$PROJECT" \
  -var="enable_cloud_run=false" \
  -var="enable_monitoring=false" \
  -var="enable_vertex_endpoint=false" \
  -var="enable_serving=false"

mkdir -p artifacts
python3 - <<PY
import datetime
from pathlib import Path
Path("artifacts/gcp_serving_off.txt").write_text(
    datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ") + " Cloud Run + monitoring disabled\n"
)
PY

echo "Cloud Run and the dashboard are off. Artifact Registry + warehouse remain."
echo "Bring back with: make gcp-up"
