#!/usr/bin/env bash
# Report whether Milestone 2 GCP secrets are injected into this agent VM.
set -euo pipefail

ok=0
echo "GCP_PROJECT_ID=${GCP_PROJECT_ID:-<unset>}"
if [[ -n "${GCP_PROJECT_ID:-}" ]]; then
  echo "  OK: project id present"
else
  echo "  MISSING: set Cursor secret GCP_PROJECT_ID (expected: production-ml-model)"
  ok=1
fi

if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" ]]; then
  # Do not print secret contents.
  bytes=$(printf '%s' "$GOOGLE_APPLICATION_CREDENTIALS_JSON" | wc -c | tr -d ' ')
  echo "GOOGLE_APPLICATION_CREDENTIALS_JSON=<present, ${bytes} bytes>"
  echo "  OK: SA JSON secret present"
else
  echo "GOOGLE_APPLICATION_CREDENTIALS_JSON=<unset>"
  echo "  MISSING: set Cursor secret GOOGLE_APPLICATION_CREDENTIALS_JSON"
  ok=1
fi

if [[ -n "${GOOGLE_APPLICATION_CREDENTIALS:-}" && -f "${GOOGLE_APPLICATION_CREDENTIALS}" ]]; then
  echo "GOOGLE_APPLICATION_CREDENTIALS=$GOOGLE_APPLICATION_CREDENTIALS (file exists)"
elif [[ -f "$PWD/sa-key.json" ]]; then
  echo "sa-key.json present in cwd (run materialize script to export path)"
else
  echo "No materialized key file yet (scripts/materialize_gcp_creds.sh)"
fi

exit "$ok"
