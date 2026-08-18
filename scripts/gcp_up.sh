#!/usr/bin/env bash
# Turn on Cloud Run + Artifact Registry + Cloud Monitoring (no Redis, no Vertex, no Composer).
# Usage: make gcp-up
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

TFDIR="$ROOT/terraform/environments/dev"
KEY="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/sa-key.json}"
REGION="${GCP_REGION:-us-central1}"

if [[ ! -f "$KEY" ]]; then
  echo "Missing GCP key at $KEY (or set GOOGLE_APPLICATION_CREDENTIALS)" >&2
  exit 1
fi
PROJECT="${GCP_PROJECT_ID:-}"
if [[ -z "$PROJECT" ]]; then
  PROJECT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['project_id'])" "$KEY")"
fi
if [[ ! -f artifacts/model.joblib || ! -f artifacts/model_meta.json ]]; then
  echo "Missing artifacts/model.joblib — train first (make train-local / existing champion)." >&2
  exit 1
fi

export GOOGLE_APPLICATION_CREDENTIALS="$KEY"
export GCP_PROJECT_ID="$PROJECT"

INVOKER="$(python3 -c "import json; print(json.load(open('$KEY'))['client_email'])")"

echo "==> auth"
gcloud auth activate-service-account --key-file="$KEY" --quiet
gcloud config set project "$PROJECT" --quiet
gcloud services enable \
  run.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  monitoring.googleapis.com \
  iamcredentials.googleapis.com \
  cloudresourcemanager.googleapis.com \
  --project="$PROJECT" --quiet

echo "==> terraform: Artifact Registry (keep across on/off)"
terraform -chdir="$TFDIR" init -input=false
terraform -chdir="$TFDIR" apply -input=false -auto-approve \
  -var="project_id=$PROJECT" \
  -var="enable_cloud_run=false" \
  -var="enable_monitoring=false" \
  -var="enable_vertex_endpoint=false" \
  -var="enable_serving=false"

IMAGE_BASE="$(terraform -chdir="$TFDIR" output -raw artifact_registry_image_base)"
TAG="$(date -u +%Y%m%dT%H%M%SZ)"
IMAGE="${IMAGE_BASE}/api:${TAG}"
echo "==> image $IMAGE"

echo "==> docker build + push"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet
DOCKER=(docker)
if ! docker info >/dev/null 2>&1; then
  DOCKER=(sudo docker)
fi
"${DOCKER[@]}" build --target serving -t "$IMAGE" "$ROOT"
"${DOCKER[@]}" push "$IMAGE"

echo "==> terraform: Cloud Run + Monitoring"
terraform -chdir="$TFDIR" apply -input=false -auto-approve \
  -var="project_id=$PROJECT" \
  -var="enable_cloud_run=true" \
  -var="enable_monitoring=true" \
  -var="enable_vertex_endpoint=false" \
  -var="enable_serving=false" \
  -var="serving_image=$IMAGE" \
  -var="invoker_sa_email=$INVOKER"

URI="$(terraform -chdir="$TFDIR" output -raw cloud_run_uri)"
DASH="$(terraform -chdir="$TFDIR" output -raw monitoring_dashboard_id)"
mkdir -p artifacts
printf '%s\n' "$URI" > artifacts/gcp_cloud_run_uri.txt
printf '%s\n' "$IMAGE" > artifacts/gcp_serving_image.txt
printf '%s\n' "$DASH" > artifacts/gcp_monitoring_dashboard.txt
python3 - <<PY
import json, datetime
from pathlib import Path
Path("artifacts/gcp_up_meta.json").write_text(json.dumps({
    "turned_on_at": datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "uri": """$URI""",
    "image": """$IMAGE""",
    "dashboard_id": """$DASH""",
    "invoker": """$INVOKER""",
    "project": """$PROJECT""",
    "region": """$REGION""",
    "min_instances": 0,
    "vertex": False,
    "redis": False,
}, indent=2) + "\n")
PY

echo "==> wait for /ready (IAM + cold start)"
sleep 8
TOKEN="$(gcloud auth print-identity-token --audiences="$URI")"
for _ in $(seq 1 48); do
  if curl -sf --max-time 30 -H "Authorization: Bearer $TOKEN" "$URI/ready" >/dev/null; then
    echo "    ready: $URI"
    break
  fi
  TOKEN="$(gcloud auth print-identity-token --audiences="$URI")"
  sleep 5
done
curl -sf --max-time 30 -H "Authorization: Bearer $TOKEN" "$URI/ready" || {
  echo "Cloud Run did not become ready: $URI" >&2
  exit 1
}

echo ""
echo "Cloud Run:  $URI"
echo "Image:      $IMAGE"
echo "Dashboard:  $DASH"
echo "Invoker:    $INVOKER (identity token; not public)"
echo "Next:       make gcp-smoke   then   make gcp-down"
