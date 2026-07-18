#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib.sh"
load_config
require_command gcloud
require_var GITHUB_REPOSITORY
WIF_POOL="${WIF_POOL:-github}"
WIF_PROVIDER="${WIF_PROVIDER:-github-provider}"
PROJECT_NUMBER="$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')"

ensure_service_account "${DEPLOY_SERVICE_ACCOUNT}" 'NeedWise GitHub Actions deployer'
bind_project_role "serviceAccount:${DEPLOY_SA_EMAIL}" roles/artifactregistry.writer
bind_project_role "serviceAccount:${DEPLOY_SA_EMAIL}" roles/compute.instanceAdmin.v1
bind_project_role "serviceAccount:${DEPLOY_SA_EMAIL}" roles/iap.tunnelResourceAccessor
bind_project_role "serviceAccount:${DEPLOY_SA_EMAIL}" roles/compute.osAdminLogin

if ! gcloud iam workload-identity-pools describe "${WIF_POOL}" --location global \
    --project "${PROJECT_ID}" >/dev/null 2>&1; then
  gcloud iam workload-identity-pools create "${WIF_POOL}" --location global \
    --project "${PROJECT_ID}" --display-name GitHub
fi
if ! gcloud iam workload-identity-pools providers describe "${WIF_PROVIDER}" \
    --workload-identity-pool "${WIF_POOL}" --location global --project "${PROJECT_ID}" \
    >/dev/null 2>&1; then
  gcloud iam workload-identity-pools providers create-oidc "${WIF_PROVIDER}" \
    --project "${PROJECT_ID}" --location global --workload-identity-pool "${WIF_POOL}" \
    --display-name 'GitHub Actions' --issuer-uri https://token.actions.githubusercontent.com \
    --attribute-mapping 'google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref' \
    --attribute-condition "assertion.repository=='${GITHUB_REPOSITORY}'"
fi
PRINCIPAL="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${GITHUB_REPOSITORY}"
if ! gcloud iam service-accounts get-iam-policy "${DEPLOY_SA_EMAIL}" --project "${PROJECT_ID}" \
    --flatten='bindings[].members' --filter="bindings.role:roles/iam.workloadIdentityUser AND bindings.members:${PRINCIPAL}" \
    --format='value(bindings.members)' | grep -Fqx "${PRINCIPAL}"; then
  gcloud iam service-accounts add-iam-policy-binding "${DEPLOY_SA_EMAIL}" --project "${PROJECT_ID}" \
    --role roles/iam.workloadIdentityUser --member "${PRINCIPAL}"
fi

PROVIDER_NAME="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/providers/${WIF_PROVIDER}"
printf '\nSet these GitHub repository variables (Settings > Secrets and variables > Actions > Variables):\n'
printf 'GCP_PROJECT_ID=%s\nGCP_REGION=%s\nGCP_ZONE=%s\nGCP_VM_NAME=%s\n' \
  "${PROJECT_ID}" "${REGION}" "${ZONE}" "${VM_NAME}"
printf 'GCP_PUBLIC_HOST=%s\n' "${DOMAIN_NAME}"
printf 'GCP_AR_REPOSITORY=%s\nGCP_SECRET_NAME=%s\nGCP_WIF_PROVIDER=%s\nGCP_DEPLOY_SERVICE_ACCOUNT=%s\n' \
  "${AR_REPOSITORY}" "${SECRET_NAME}" "${PROVIDER_NAME}" "${DEPLOY_SA_EMAIL}"
