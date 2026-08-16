#!/usr/bin/env bash
# Thin API smoke for decision/agent demos (server must already be up).
set -euo pipefail

BASE="${API_BASE:-http://127.0.0.1:8080}"
HDR=(-H 'Content-Type: application/json')
if [[ -n "${API_KEY:-}" ]]; then
  HDR+=(-H "X-API-Key: ${API_KEY}")
fi

echo "== health =="
curl -sf "${BASE}/health" | python -m json.tool

PRED=$(curl -sf "${BASE}/v1/predict" "${HDR[@]}" -d '{
  "order_id":"walkthrough-1",
  "seller_id":"s1",
  "purchase_timestamp":"2018-06-01T12:00:00Z",
  "item_count":2,
  "basket_value":280,
  "freight_value":22,
  "estimated_delivery_horizon_days":14
}')
echo "== predict =="
echo "$PRED" | python -m json.tool

PID=$(echo "$PRED" | python -c 'import json,sys; print(json.load(sys.stdin)["prediction_id"])')
MVER=$(echo "$PRED" | python -c 'import json,sys; print(json.load(sys.stdin)["model_version"])')
PROBA=$(echo "$PRED" | python -c 'import json,sys; print(json.load(sys.stdin)["long_delivery_probability"])')

echo "== decision =="
curl -sf "${BASE}/v1/decision" "${HDR[@]}" -d "{
  \"order_id\":\"walkthrough-1\",
  \"seller_id\":\"s1\",
  \"purchase_timestamp\":\"2018-06-01T12:00:00Z\",
  \"item_count\":2,
  \"basket_value\":280,
  \"freight_value\":22,
  \"estimated_delivery_horizon_days\":14,
  \"simulate\": false
}" | python -m json.tool

echo "== agent review (human approved) =="
curl -sf "${BASE}/v1/agent/review" "${HDR[@]}" -d "{
  \"order_id\":\"walkthrough-1\",
  \"prediction_id\":\"${PID}\",
  \"model_version\":\"${MVER}\",
  \"long_delivery_probability\": ${PROBA},
  \"basket_value\": 280,
  \"require_human_approval\": true,
  \"human_approved\": true,
  \"run_simulation\": false
}" | python -m json.tool

echo "== metrics (decision slice) =="
curl -sf "${BASE}/v1/metrics" | python -c 'import json,sys; print(json.dumps(json.load(sys.stdin).get("decision",{}), indent=2))'
