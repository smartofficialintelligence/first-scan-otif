#!/usr/bin/env bash
# Capture live GCP serving proof (no secrets) into docs/evidence/.
# Run while Cloud Run is up (after gcp-smoke), then again after gcp-down with --after-down.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

AFTER_DOWN=false
if [[ "${1:-}" == "--after-down" ]]; then
  AFTER_DOWN=true
fi

OUT="docs/evidence/gcp-serving-run.md"
mkdir -p docs/evidence artifacts

KEY="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/sa-key.json}"
if [[ ! -f "$KEY" ]]; then
  echo "Missing GCP key at $KEY" >&2
  exit 1
fi
PROJECT="${GCP_PROJECT_ID:-}"
if [[ -z "$PROJECT" ]]; then
  PROJECT="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['project_id'])" "$KEY")"
fi
REGION="${GCP_REGION:-us-central1}"
export GOOGLE_APPLICATION_CREDENTIALS="$KEY"
gcloud auth activate-service-account --key-file="$KEY" --quiet
gcloud config set project "$PROJECT" --quiet

URI=""
IMAGE=""
DASH=""
[[ -f artifacts/gcp_cloud_run_uri.txt ]] && URI="$(tr -d '[:space:]' < artifacts/gcp_cloud_run_uri.txt)"
[[ -f artifacts/gcp_serving_image.txt ]] && IMAGE="$(tr -d '[:space:]' < artifacts/gcp_serving_image.txt)"
[[ -f artifacts/gcp_monitoring_dashboard.txt ]] && DASH="$(tr -d '[:space:]' < artifacts/gcp_monitoring_dashboard.txt)"

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if [[ "$AFTER_DOWN" == true ]]; then
  RUN_LIST="$(gcloud run services list --region="$REGION" --project="$PROJECT" --format='value(metadata.name)' 2>/dev/null || true)"
  TF_URI="$(terraform -chdir=terraform/environments/dev output -raw cloud_run_uri 2>/dev/null || true)"
  TF_DASH="$(terraform -chdir=terraform/environments/dev output -raw monitoring_dashboard_id 2>/dev/null || true)"
  export EVIDENCE_OUT="$OUT" EVIDENCE_NOW="$NOW" EVIDENCE_RUN_LIST="${RUN_LIST:-}" EVIDENCE_TF_URI="${TF_URI:-}" EVIDENCE_TF_DASH="${TF_DASH:-}"
  python3 - <<'PY'
import json
import os
from pathlib import Path

p = Path(os.environ["EVIDENCE_OUT"])
text = p.read_text() if p.exists() else "# GCP serving proof\n\n"
project = ""
meta = Path("artifacts/gcp_up_meta.json")
if meta.exists():
    project = json.loads(meta.read_text()).get("project") or ""

def redact(s: str) -> str:
    t = s or ""
    return t.replace(project, "<gcp-project>") if project else t

run_list = redact(os.environ.get("EVIDENCE_RUN_LIST") or "") or "(none)"
tf_uri = redact(os.environ.get("EVIDENCE_TF_URI") or "") or "null"
tf_dash = redact(os.environ.get("EVIDENCE_TF_DASH") or "") or "null"
now = os.environ["EVIDENCE_NOW"]
block = f"""

## Turned off

- Timestamp (UTC): {now}
- gcloud run services list names: {run_list}
- Terraform cloud_run_uri: `{tf_uri}`
- Terraform monitoring_dashboard_id: `{tf_dash}`
- Artifact Registry and warehouse (BQ / GCS / IAM) were left in place so make gcp-up can turn serving back on.

"""
if "## Turned off" in text:
    text = text.split("## Turned off")[0].rstrip() + "\n" + block
else:
    text = text.rstrip() + "\n" + block
p.write_text(text)
print(f"updated {p} (after-down)")
PY
  exit 0
fi

if [[ -z "$URI" ]]; then
  echo "No Cloud Run URI — run make gcp-up first." >&2
  exit 1
fi

TOKEN="$(gcloud auth print-identity-token --audiences="$URI")"
AUTH=(-H "Authorization: Bearer $TOKEN")
curl -sf --max-time 30 "${AUTH[@]}" "$URI/health" > artifacts/gcp_health.json
curl -sf --max-time 30 "${AUTH[@]}" "$URI/ready" > artifacts/gcp_ready.json
curl -sf --max-time 30 "${AUTH[@]}" "$URI/v1/model" > artifacts/gcp_model.json

gcloud run services describe olist-ml-api \
  --region="$REGION" --project="$PROJECT" \
  --format=json > artifacts/gcp_run_describe.json

if [[ -n "$DASH" && "$DASH" != "null" ]]; then
  gcloud monitoring dashboards describe "$DASH" --project="$PROJECT" --format=json \
    > artifacts/gcp_dashboard_describe.json || true
fi

python3 - <<'PY'
import json
from pathlib import Path

uri = Path("artifacts/gcp_cloud_run_uri.txt").read_text().strip()
image = Path("artifacts/gcp_serving_image.txt").read_text().strip()
dash = Path("artifacts/gcp_monitoring_dashboard.txt").read_text().strip()
health = json.loads(Path("artifacts/gcp_health.json").read_text())
ready = json.loads(Path("artifacts/gcp_ready.json").read_text())
model = json.loads(Path("artifacts/gcp_model.json").read_text())
desc = json.loads(Path("artifacts/gcp_run_describe.json").read_text())
meta = {}
if Path("artifacts/gcp_up_meta.json").exists():
    meta = json.loads(Path("artifacts/gcp_up_meta.json").read_text())

project = str(meta.get("project") or "")

def redact(value):
    text = "" if value is None else str(value)
    if project:
        text = text.replace(project, "<gcp-project>")
    return text

rows = []
logp = Path("artifacts/prediction_logs_gcp.jsonl")
if logp.exists():
    rows = [json.loads(l) for l in logp.read_text().splitlines() if l.strip()]
ok = sum(1 for r in rows if r.get("http_status") == 200)
versions = sorted({r.get("model_version") for r in rows if r.get("model_version")})
lat = [r.get("latency_ms") for r in rows if isinstance(r.get("latency_ms"), (int, float))]
p95 = None
if lat:
    s = sorted(lat)
    p95 = s[min(len(s) - 1, int(round(0.95 * (len(s) - 1))))]

spec = (((desc.get("spec") or {}).get("template") or {}).get("spec") or {})
containers = spec.get("containers") or []
img_live = containers[0].get("image") if containers else None
scaling = ((desc.get("spec") or {}).get("template") or {}).get("scaling") or spec.get("scaling") or {}
# Cloud Run Admin API v1 vs v2 shape
min_c = (
    scaling.get("minInstanceCount")
    or ((desc.get("spec") or {}).get("template") or {}).get("scaling", {}).get("minInstanceCount")
)
# v1 describe
template = (desc.get("spec") or {}).get("template") or {}
annotations = (template.get("metadata") or {}).get("annotations") or {}
min_anno = annotations.get("autoscaling.knative.dev/minScale", "0")

dash_name = None
if Path("artifacts/gcp_dashboard_describe.json").exists():
    try:
        djson = json.loads(Path("artifacts/gcp_dashboard_describe.json").read_text())
        dash_name = djson.get("displayName")
    except json.JSONDecodeError:
        pass

mcp_line = None
mcp_path = Path("artifacts/gcp_mcp_smoke.txt")
if mcp_path.exists():
    mcp_line = mcp_path.read_text().strip().splitlines()[-1] if mcp_path.read_text().strip() else None

now = __import__("datetime").datetime.now(__import__("datetime").UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

md = f"""# GCP serving proof

One live Cloud Run + Cloud Monitoring run of the champion promise-miss API.
Turned **on**, exercised, recorded here, then turned **off**. Redis / Vertex Endpoint / Composer were not created.

Captured: `{now}` (UTC)

## What was on

| Item | Value |
|---|---|
| Region | `us-central1` |
| Cloud Run service | `olist-ml-api` |
| URI | `{redact(uri)}` |
| Image | `{redact(image)}` |
| Live revision image | `{redact(img_live)}` |
| Min instances | `{min_anno}` (Terraform `min_instance_count = 0`) |
| Auth | Not public. Identity token as `roles/run.invoker` (IAM). App `AUTH_MODE=off`. |
| Dashboard | `{redact(dash)}` |
| Dashboard display name | `{dash_name}` |
| Turned on at | `{meta.get("turned_on_at")}` |

## REST

`GET /health` → `{json.dumps(health)}`

`GET /ready` → `{json.dumps(ready)}`

`GET /v1/model`

- `model_version`: `{model.get("model_version")}`
- `ready`: `{model.get("ready")}`
- feature count: `{len(model.get("feature_names") or [])}`

Champion artifact baked into the serving image: `artifacts/model.joblib` (`local-20260818T041243Z` when this proof was first recorded).

## MCP

Streamable HTTP on the same Cloud Run service (`POST /mcp`, identity token). Same `PredictionService` as REST.

```
{mcp_line or "(see make gcp-smoke stdout)"}
```

## Holdout replay through Cloud Run

50 chronological holdout events, HTTP `POST /v1/predict`, identity token.

| Metric | Value |
|---|---|
| Rows | {len(rows)} |
| HTTP 200 | {ok} |
| model_version values | {", ".join(str(v) for v in versions) or "(none)"} |
| p95 latency_ms (client) | {f"{p95:.1f}" if p95 is not None else "n/a"} |

Log path (gitignored): `artifacts/prediction_logs_gcp.jsonl`

## Left off on purpose

- Redis / Memorystore (Feast online stays SQLite)
- Vertex AI Endpoint (API scores the joblib in the container)
- Cloud Composer
- Hosted MLflow
- Cloud Run min instances > 0
- Public `allUsers` invoker

## Turn back on later

```text
make gcp-up      # Artifact Registry (kept) + build/push + Cloud Run + dashboard
make gcp-smoke   # REST + MCP + 50-event HTTP replay
make gcp-evidence
make gcp-down    # destroy Cloud Run + dashboard; keep registry + warehouse
```

Warehouse (BigQuery / GCS / IAM) is independent and already applied.
"""
Path("docs/evidence/gcp-serving-run.md").write_text(md)
print("wrote docs/evidence/gcp-serving-run.md")
PY
