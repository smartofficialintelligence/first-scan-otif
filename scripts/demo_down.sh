#!/usr/bin/env bash
# Tear down local demo API. Does not delete GCP resources unless you run teardown with --apply.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PID_FILE="artifacts/api.pid"

echo "==> demo_down: stop local uvicorn"
if [[ -f "$PID_FILE" ]]; then
  PID="$(cat "$PID_FILE" || true)"
  if [[ -n "${PID}" ]] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" || true
    fi
    echo "    stopped pid=$PID"
  else
    echo "    stale pid file (process not running)"
  fi
  rm -f "$PID_FILE"
else
  echo "    no artifacts/api.pid — nothing to kill"
fi

echo ""
echo "Teardown reminders (manual — not deleting GCP without explicit flags):"
echo "  - Cloud Run (live proof): make gcp-down"
echo "  - Vertex Endpoint: uv run python scripts/teardown_endpoint.py --dry-run"
echo "    (pass --apply only when GCP credentials are set and you intend to undeploy)"
echo "  - Redis / Feast online: stop any demo Redis; SQLite files under data/feast are local-only"
echo "  - Composer / Airflow: pause DAGs; do not delete Composer env without H7"
echo "  - Cloud Run: make gcp-down (destroys the service; keeps Artifact Registry)"
echo "  - Terraform: do not terraform destroy without review; idle cost target is ~\$0 after down"
