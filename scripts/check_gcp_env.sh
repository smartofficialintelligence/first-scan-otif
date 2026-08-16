#!/usr/bin/env bash
# Report whether Milestone 2 GCP secrets are injected into this agent VM.
set -euo pipefail

ok=0
# Trim accidental whitespace from Cursor secret injection (do not mutate caller env).
_project="$(printf '%s' "${GCP_PROJECT_ID:-}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
_json="$(printf '%s' "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

echo "GCP_PROJECT_ID=${_project:-<unset>}"
if [[ -n "${_project}" ]]; then
  echo "  OK: project id present"
  if [[ "${GCP_PROJECT_ID}" != "${_project}" ]]; then
    echo "  WARN: GCP_PROJECT_ID had surrounding whitespace (trimmed for checks)"
  fi
else
  echo "  MISSING: set Cursor secret GCP_PROJECT_ID (expected: production-ml-model)"
  ok=1
fi

if [[ -n "${_json}" ]]; then
  # Do not print secret contents.
  bytes=$(printf '%s' "$_json" | wc -c | tr -d ' ')
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
