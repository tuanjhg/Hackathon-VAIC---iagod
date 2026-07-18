#!/usr/bin/env bash
set -Eeuo pipefail

GCP_SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${GCP_CONFIG_FILE:-${GCP_SCRIPT_DIR}/config.env}"

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
info() { printf '\n==> %s\n' "$*"; }
require_command() { command -v "$1" >/dev/null 2>&1 || die "Missing command: $1"; }
require_var() { [[ -n "${!1:-}" ]] || die "Missing $1 in ${CONFIG_FILE}"; }

load_config() {
  [[ -f "${CONFIG_FILE}" ]] || die "Copy config.example.env to ${CONFIG_FILE} and edit it"
  # shellcheck disable=SC1090
  source "${CONFIG_FILE}"
  for name in PROJECT_ID REGION ZONE VM_NAME MACHINE_TYPE STATIC_IP_NAME AR_REPOSITORY \
    RUNTIME_SERVICE_ACCOUNT DEPLOY_SERVICE_ACCOUNT SECRET_NAME DOMAIN_NAME; do
    require_var "${name}"
  done
  BOOT_DISK_SIZE="${BOOT_DISK_SIZE:-50GB}"
  RUNTIME_SA_EMAIL="${RUNTIME_SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
  DEPLOY_SA_EMAIL="${DEPLOY_SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
  AR_HOST="${REGION}-docker.pkg.dev"
  IMAGE_PREFIX="${AR_HOST}/${PROJECT_ID}/${AR_REPOSITORY}"
}

ensure_service_account() {
  local account_id="$1" display_name="$2"
  if ! gcloud iam service-accounts describe "${account_id}@${PROJECT_ID}.iam.gserviceaccount.com" \
      --project "${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${account_id}" --project "${PROJECT_ID}" \
      --display-name "${display_name}"
  fi
}

bind_project_role() {
  local member="$1" role="$2"
  gcloud projects add-iam-policy-binding "${PROJECT_ID}" --member "${member}" --role "${role}" \
    --condition=None --quiet >/dev/null
}
