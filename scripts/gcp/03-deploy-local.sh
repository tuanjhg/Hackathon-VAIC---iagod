#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd)"
source "${SCRIPT_DIR}/lib.sh"
load_config
require_command gcloud
require_command docker
TAG="${1:-$(git -C "${REPO_ROOT}" rev-parse --short=12 HEAD)}"

info "Configuring Docker and building immutable images ${TAG}"
gcloud auth configure-docker "${AR_HOST}" --quiet
docker build -f "${REPO_ROOT}/apps/api/Dockerfile.prod" -t "${IMAGE_PREFIX}/api:${TAG}" "${REPO_ROOT}"
docker build --build-arg NEXT_PUBLIC_API_URL=/api/v1 -t "${IMAGE_PREFIX}/web:${TAG}" "${REPO_ROOT}/apps/web"
docker push "${IMAGE_PREFIX}/api:${TAG}"
docker push "${IMAGE_PREFIX}/web:${TAG}"

info "Copying deployment manifest and rolling out through IAP"
gcloud compute scp "${REPO_ROOT}/deploy/docker-compose.prod.yml" \
  "${SCRIPT_DIR}/remote-deploy.sh" "${VM_NAME}:/tmp/" --project "${PROJECT_ID}" \
  --zone "${ZONE}" --tunnel-through-iap
gcloud compute ssh "${VM_NAME}" --project "${PROJECT_ID}" --zone "${ZONE}" \
  --tunnel-through-iap --command \
  "sudo bash /tmp/remote-deploy.sh '${PROJECT_ID}' '${REGION}' '${AR_REPOSITORY}' '${TAG}' '${SECRET_NAME}' '${SITE_SCHEME:-https}' '${DOMAIN_NAME}'"
