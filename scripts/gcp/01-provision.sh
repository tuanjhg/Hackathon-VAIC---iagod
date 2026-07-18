#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib.sh
source "${SCRIPT_DIR}/lib.sh"
load_config
require_command gcloud

info "Checking gcloud authentication and project"
gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q . \
  || die 'Run: gcloud auth login'
gcloud projects describe "${PROJECT_ID}" >/dev/null
gcloud config set project "${PROJECT_ID}" >/dev/null
gcloud config set compute/region "${REGION}" >/dev/null
gcloud config set compute/zone "${ZONE}" >/dev/null

info "Enabling required APIs"
gcloud services enable compute.googleapis.com artifactregistry.googleapis.com \
  secretmanager.googleapis.com iamcredentials.googleapis.com sts.googleapis.com \
  iap.googleapis.com --project "${PROJECT_ID}"

info "Creating Artifact Registry and runtime identity"
if ! gcloud artifacts repositories describe "${AR_REPOSITORY}" --location "${REGION}" \
    --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud artifacts repositories create "${AR_REPOSITORY}" --repository-format=docker \
    --location "${REGION}" --description 'NeedWise production images' --project "${PROJECT_ID}"
fi
ensure_service_account "${RUNTIME_SERVICE_ACCOUNT}" 'NeedWise Compute Engine runtime'
bind_project_role "serviceAccount:${RUNTIME_SA_EMAIL}" roles/artifactregistry.reader
bind_project_role "serviceAccount:${RUNTIME_SA_EMAIL}" roles/secretmanager.secretAccessor
bind_project_role "serviceAccount:${RUNTIME_SA_EMAIL}" roles/logging.logWriter
bind_project_role "serviceAccount:${RUNTIME_SA_EMAIL}" roles/monitoring.metricWriter

info "Reserving static IPv4 address"
if ! gcloud compute addresses describe "${STATIC_IP_NAME}" --region "${REGION}" \
    --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud compute addresses create "${STATIC_IP_NAME}" --region "${REGION}" --project "${PROJECT_ID}"
fi
STATIC_IP="$(gcloud compute addresses describe "${STATIC_IP_NAME}" --region "${REGION}" \
  --project "${PROJECT_ID}" --format='value(address)')"

info "Creating least-exposed firewall rules"
if ! gcloud compute firewall-rules describe needwise-web-ingress --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud compute firewall-rules create needwise-web-ingress --project "${PROJECT_ID}" \
    --network default --direction INGRESS --priority 1000 --action ALLOW \
    --rules tcp:80,tcp:443 --source-ranges 0.0.0.0/0 --target-tags needwise-web
fi
if ! gcloud compute firewall-rules describe needwise-iap-ssh --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud compute firewall-rules create needwise-iap-ssh --project "${PROJECT_ID}" \
    --network default --direction INGRESS --priority 1000 --action ALLOW --rules tcp:22 \
    --source-ranges 35.235.240.0/20 --target-tags needwise-web
fi

info "Creating Compute Engine VM"
if ! gcloud compute instances describe "${VM_NAME}" --zone "${ZONE}" --project "${PROJECT_ID}" \
    >/dev/null 2>&1; then
  gcloud compute instances create "${VM_NAME}" --project "${PROJECT_ID}" --zone "${ZONE}" \
    --machine-type "${MACHINE_TYPE}" --image-family ubuntu-2404-lts-amd64 \
    --image-project ubuntu-os-cloud --boot-disk-type pd-balanced \
    --boot-disk-size "${BOOT_DISK_SIZE}" --address "${STATIC_IP}" --tags needwise-web \
    --service-account "${RUNTIME_SA_EMAIL}" --scopes cloud-platform \
    --metadata enable-oslogin=TRUE --metadata-from-file startup-script="${SCRIPT_DIR}/startup.sh" \
    --shielded-secure-boot --shielded-vtpm --shielded-integrity-monitoring \
    --maintenance-policy MIGRATE --provisioning-model STANDARD
fi

printf '\nProvisioning complete.\nPublic IP: %s\nDNS A record: %s -> %s\n' \
  "${STATIC_IP}" "${DOMAIN_NAME}" "${STATIC_IP}"
printf 'Wait for bootstrap: gcloud compute ssh %s --zone %s --tunnel-through-iap --command "test -f /var/log/needwise-startup-complete"\n' \
  "${VM_NAME}" "${ZONE}"
