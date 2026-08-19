#!/usr/bin/env bash
# Smoke REST + Streamable HTTP MCP on Cloud Run (same PredictionService / champion).
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

echo "==> MCP Streamable HTTP on Cloud Run (/mcp)"
uv run python - <<'PY' | tee artifacts/gcp_mcp_smoke.txt
import json, os, urllib.request

uri = os.environ["URI"].rstrip("/")
token = os.environ["TOKEN"]
headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def rpc(payload: dict) -> dict:
    req = urllib.request.Request(
        uri + "/mcp",
        data=json.dumps(payload).encode(),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        ctype = resp.headers.get("Content-Type", "")
        raw = resp.read().decode()
    if "text/event-stream" in ctype:
        for line in raw.splitlines():
            if line.startswith("data:"):
                body = json.loads(line[5:].strip())
                if isinstance(body, dict) and ("result" in body or "error" in body):
                    return body
        raise SystemExit(f"no JSON-RPC in SSE: {raw[:500]}")
    return json.loads(raw)


init = rpc({
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
        "protocolVersion": "2025-03-26",
        "capabilities": {},
        "clientInfo": {"name": "gcp-smoke", "version": "0"},
    },
})
assert init.get("result", {}).get("serverInfo", {}).get("name") == "olist-ml", init

status = rpc({
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/call",
    "params": {"name": "get_model_status", "arguments": {}},
})
text = "".join(
    p.get("text", "")
    for p in status.get("result", {}).get("content", [])
    if p.get("type") == "text"
)
body = json.loads(text)
assert body.get("ready") is True, body

score = rpc({
    "jsonrpc": "2.0",
    "id": 3,
    "method": "tools/call",
    "params": {
        "name": "predict_promise_miss",
        "arguments": {
            "order_id": "mcp-smoke",
            "seller_id": "unknown",
            "purchase_timestamp": "2018-07-19T08:58:48+00:00",
            "prediction_timestamp": "2018-07-19T09:10:16+00:00",
            "item_count": 1,
            "basket_value": 100.0,
            "freight_value": 10.0,
            "estimated_delivery_horizon_days": 14.0,
            "geo_distance_km": 50.0,
        },
    },
})
pred_text = "".join(
    p.get("text", "")
    for p in score.get("result", {}).get("content", [])
    if p.get("type") == "text"
)
pred = json.loads(pred_text)
expl = rpc({
    "jsonrpc": "2.0",
    "id": 4,
    "method": "tools/call",
    "params": {
        "name": "explain_promise_miss",
        "arguments": {
            "order_id": "mcp-smoke",
            "seller_id": "unknown",
            "purchase_timestamp": "2018-07-19T08:58:48+00:00",
            "prediction_timestamp": "2018-07-19T09:10:16+00:00",
            "item_count": 2,
            "basket_value": 280.0,
            "freight_value": 42.0,
            "estimated_delivery_horizon_days": 8.0,
            "customer_state": "SP",
            "seller_state_primary": "RJ",
            "geo_distance_km": 250.0,
            "seller_late_rate_30d": 0.35,
            "handling_days": 3.0,
            "remaining_to_promise_days": 4.0,
        },
    },
})
expl_text = "".join(
    p.get("text", "")
    for p in expl.get("result", {}).get("content", [])
    if p.get("type") == "text"
)
explained = json.loads(expl_text)
assert explained.get("method") == "shap", explained
top = explained.get("top_features") or []
assert any(abs(float(f.get("contribution") or 0)) > 0 for f in top), explained
lead = top[0] if top else {}
print(
    f"mcp_http model={body.get('model_version')} "
    f"p={float(pred['promise_miss_probability']):.4f} band={pred['risk_band']}"
)
print(
    f"mcp_shap method={explained['method']} "
    f"top={lead.get('feature')} contrib={float(lead.get('contribution') or 0):+.4f}"
)
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
