#!/usr/bin/env bash
# Materialize GCP ADC from Cursor secrets into a local key file (gitignored).
# Expects:
#   GCP_PROJECT_ID
#   GOOGLE_APPLICATION_CREDENTIALS_JSON  (raw JSON string)
set -euo pipefail

if [[ -z "${GCP_PROJECT_ID:-}" ]]; then
  echo "GCP_PROJECT_ID is not set" >&2
  exit 1
fi
if [[ -z "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" ]]; then
  echo "GOOGLE_APPLICATION_CREDENTIALS_JSON is not set" >&2
  exit 1
fi

KEY_PATH="${GOOGLE_APPLICATION_CREDENTIALS:-$PWD/sa-key.json}"
printf '%s' "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > "$KEY_PATH"
chmod 600 "$KEY_PATH"
export GOOGLE_APPLICATION_CREDENTIALS="$KEY_PATH"
echo "Wrote credentials to $KEY_PATH"
echo "GCP_PROJECT_ID=$GCP_PROJECT_ID"
echo "GOOGLE_APPLICATION_CREDENTIALS=$GOOGLE_APPLICATION_CREDENTIALS"
