#!/usr/bin/env bash
# Smoke REST on Cloud Run + MCP locally (same PredictionService / champion).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

URI="${1:-}"
if [[ -z "$URI" && -f artifacts/gcp_cloud_run_uri.txt ]]; then
  URI="$(tr -d '[:space:]' < artifacts/gcp_cloud_run_uri.txt)"
fi
if [[ -z "$URI" ]]; then
  echo "Pass Cloud Run URI or run make gcp-up first." >&2
  exit 1
fi

KEY="${GOOGLE_APPLICATION_CREDENTIALS:-$ROOT/sa-key.json}"
export GOOGLE_APPLICATION_CREDENTIALS="$KEY"
gcloud auth activate-service-account --key-file="$KEY" --quiet
TOKEN="$(gcloud auth print-identity-token --audiences="$URI")"
AUTH=(-H "Authorization: Bearer $TOKEN")
export URI TOKEN
mkdir -p artifacts

echo "==> REST /health"
curl -sf --max-time 30 "${AUTH[@]}" "$URI/health" | python3 -m json.tool
echo "==> REST /ready"
curl -sf --max-time 30 "${AUTH[@]}" "$URI/ready" | python3 -m json.tool
echo "==> REST /v1/model"
curl -sf --max-time 30 "${AUTH[@]}" "$URI/v1/model" | tee artifacts/gcp_model.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['model_version'], 'ready', d['ready'])"

echo "==> REST /v1/predict (one holdout row)"
uv run python - <<PY
import json, os, urllib.request
import pandas as pd

uri = os.environ["URI"]
token = os.environ["TOKEN"]
df = pd.read_csv("artifacts/replay_holdout.csv")
row = df.iloc[0]
seller = str(row.get("seller_id") or row.get("primary_seller_id"))
payload = {
    "order_id": str(row["order_id"]),
    "seller_id": seller,
    "purchase_timestamp": str(pd.Timestamp(row["order_purchase_timestamp"]).isoformat()),
    "prediction_timestamp": str(pd.Timestamp(row["prediction_ts"]).isoformat()),
    "item_count": int(row["item_count"]),
    "basket_value": float(row["basket_value"]),
    "freight_value": float(row["freight_value"]),
    "seller_count": int(row["seller_count"]),
    "category_count": int(row["category_count"]),
    "payment_type_primary": str(row["payment_type_primary"]),
    "installment_count": int(row["installment_count"]),
    "estimated_delivery_horizon_days": float(row["estimated_delivery_horizon_days"]),
    "customer_state": str(row["customer_state"]),
    "seller_state_primary": str(row["seller_state_primary"]),
    "geo_distance_km": float(row["geo_distance_km"]),
}
for k in (
    "handling_days", "remaining_to_promise_days", "handling_frac_of_promise", "limit_miss",
    "same_state", "seller_order_count_7d", "seller_order_count_30d", "seller_order_count_90d",
    "seller_late_rate_7d", "seller_late_rate_30d", "seller_late_rate_90d",
):
    if k in row and pd.notna(row[k]):
        payload[k] = float(row[k])
req = urllib.request.Request(
    uri.rstrip("/") + "/v1/predict",
    data=json.dumps(payload).encode(),
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
)
print(urllib.request.urlopen(req, timeout=60).read().decode())
PY

echo "==> MCP (local process, same champion artifact as the image)"
uv run python - <<'PY' | tee artifacts/gcp_mcp_smoke.txt
from olist_ml.api.mcp_server import get_service
from olist_ml.schemas import PredictRequest
from datetime import datetime, timezone

svc = get_service()
assert svc.ready, "MCP PredictionService not ready"
req = PredictRequest(
    order_id="mcp-smoke",
    seller_id="unknown",
    purchase_timestamp=datetime(2018, 7, 19, 8, 58, 48, tzinfo=timezone.utc),
    prediction_timestamp=datetime(2018, 7, 19, 9, 10, 16, tzinfo=timezone.utc),
    item_count=1,
    basket_value=100.0,
    freight_value=10.0,
    estimated_delivery_horizon_days=14.0,
    geo_distance_km=50.0,
)
resp = svc.predict_one(req)
print(f"mcp_ready model={resp.model_version} p={resp.promise_miss_probability:.4f} band={resp.risk_band}")
PY

echo "==> holdout replay through Cloud Run (50 events)"
uv run python scripts/replay_traffic.py \
  --inprocess false \
  --base-url "${URI}/v1/predict" \
  --bearer-token "$TOKEN" \
  --no-challenger \
  --max-events 50 \
  --scenario baseline \
  --log-path artifacts/prediction_logs_gcp.jsonl \
  --snapshot-id gcp-live

python3 - <<'PY'
import json
from pathlib import Path
rows = [json.loads(l) for l in Path("artifacts/prediction_logs_gcp.jsonl").read_text().splitlines() if l.strip()]
ok = sum(1 for r in rows if r.get("http_status") == 200)
print(f"replay_rows={len(rows)} http_200={ok} versions={sorted({r.get('model_version') for r in rows})}")
PY

echo "gcp-smoke ok"
