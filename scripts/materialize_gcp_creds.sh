#!/usr/bin/env bash
# Materialize GCP ADC from Cursor secrets into a local key file (gitignored).
# Expects:
#   GCP_PROJECT_ID
#   GOOGLE_APPLICATION_CREDENTIALS_JSON  (raw JSON string)
#
# Usage (safe to source):
#   source <(bash scripts/materialize_gcp_creds.sh)
# Status messages go to stderr; only export lines go to stdout.
set -euo pipefail

# Trim accidental whitespace from Cursor secret injection.
GCP_PROJECT_ID="$(printf '%s' "${GCP_PROJECT_ID:-}" | tr -d '\r\n' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
GOOGLE_APPLICATION_CREDENTIALS_JSON="$(printf '%s' "${GOOGLE_APPLICATION_CREDENTIALS_JSON:-}" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"

if [[ -z "${GCP_PROJECT_ID}" ]]; then
  echo "GCP_PROJECT_ID is not set" >&2
  exit 1
fi
if [[ -z "${GOOGLE_APPLICATION_CREDENTIALS_JSON}" ]]; then
  echo "GOOGLE_APPLICATION_CREDENTIALS_JSON is not set" >&2
  exit 1
fi

KEY_PATH="${GOOGLE_APPLICATION_CREDENTIALS:-$PWD/sa-key.json}"
printf '%s' "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > "$KEY_PATH"
chmod 600 "$KEY_PATH"

echo "Wrote credentials to $KEY_PATH" >&2
echo "GCP_PROJECT_ID=$GCP_PROJECT_ID" >&2
echo "GOOGLE_APPLICATION_CREDENTIALS=$KEY_PATH" >&2

# Emit only shell assignments for `source <(...)`.
printf 'export GOOGLE_APPLICATION_CREDENTIALS=%q\n' "$KEY_PATH"
printf 'export GCP_PROJECT_ID=%q\n' "$GCP_PROJECT_ID"
