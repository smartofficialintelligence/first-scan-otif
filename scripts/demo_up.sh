#!/usr/bin/env bash
# Bring up local demo serving (idempotent-ish). Does not apply Terraform or Vertex.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

mkdir -p artifacts
PID_FILE="artifacts/api.pid"
PORT="${PORT:-8080}"
HOST="${HOST:-0.0.0.0}"

echo "==> demo_up: materialize note"
echo "    Feast: run 'make feast-apply' (demo-off uses SQLite online store)."
echo "    Vertex Endpoint / Cloud Run: enable via terraform enable_serving=true (not applied here)."

echo "==> sync deps"
if command -v uv >/dev/null 2>&1; then
  uv sync --all-extras
else
  echo "uv not found; skipping sync" >&2
fi

if [[ ! -f artifacts/model.joblib || ! -f artifacts/model_meta.json ]]; then
  echo "==> no champion artifact; train-local + promote (demo approver)"
  make train-local
  uv run python scripts/promote_candidate.py --approved-by "demo_up.sh" \
    --note "local demo bootstrap — not a production promote"
else
  echo "==> artifact present at artifacts/model.joblib"
fi

if [[ -f "$PID_FILE" ]]; then
  OLD_PID="$(cat "$PID_FILE" || true)"
  if [[ -n "${OLD_PID}" ]] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "==> uvicorn already running (pid=$OLD_PID); leaving it up"
    echo ""
    echo "Next steps:"
    echo "  - Smoke: make smoke-local"
    echo "  - Feast online (optional): make feast-apply"
    echo "  - Vertex: terraform enable_serving=true + scripts/teardown_endpoint.py --dry-run"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

echo "==> start uvicorn on ${HOST}:${PORT}"
# shellcheck disable=SC2086
nohup uv run uvicorn olist_ml.api.app:app --host "$HOST" --port "$PORT" \
  >artifacts/api.log 2>&1 &
echo $! >"$PID_FILE"
sleep 1
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "    pid=$(cat "$PID_FILE") log=artifacts/api.log"
else
  echo "uvicorn failed to start; see artifacts/api.log" >&2
  exit 1
fi

echo ""
echo "Next steps:"
echo "  - Smoke: make smoke-local  (or curl http://127.0.0.1:${PORT}/health)"
echo "  - Predict: POST /v1/predict  |  Explain: POST /v1/explain"
echo "  - Feast (optional): make feast-apply / feast-historical"
echo "  - Vertex Endpoint: set enable_serving=true in terraform (do not apply without H7)"
echo "  - Tear down local API: make demo-down"
