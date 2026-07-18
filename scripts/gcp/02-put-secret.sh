#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"
load_config
require_command gcloud
ENV_FILE="${1:-}"
[[ -n "${ENV_FILE}" && -f "${ENV_FILE}" ]] || die "Usage: $0 /path/to/prod.env"
chmod go-rwx "${ENV_FILE}" 2>/dev/null || true

if ! gcloud secrets describe "${SECRET_NAME}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud secrets create "${SECRET_NAME}" --replication-policy automatic --project "${PROJECT_ID}"
fi
gcloud secrets versions add "${SECRET_NAME}" --data-file "${ENV_FILE}" --project "${PROJECT_ID}"
info "Added a new immutable version to Secret Manager; local file was not uploaded elsewhere"
