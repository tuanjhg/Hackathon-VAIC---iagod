#!/usr/bin/env bash
set -Eeuo pipefail
[[ $# -eq 7 ]] || { echo 'Expected PROJECT REGION REPOSITORY TAG SECRET SITE_SCHEME DOMAIN'; exit 2; }
PROJECT_ID="$1"; REGION="$2"; REPOSITORY="$3"; TAG="$4"; SECRET_NAME="$5"
SITE_SCHEME="$6"; DOMAIN_NAME="$7"
DEPLOY_DIR=/opt/needwise
COMPOSE_FILE="${DEPLOY_DIR}/docker-compose.prod.yml"
PREVIOUS_TAG=""

rollback() {
  local exit_code=$?
  trap - ERR
  if [[ -n "${PREVIOUS_TAG}" && -f "${DEPLOY_DIR}/.env.previous" ]]; then
    echo "Deployment failed; rolling containers back to ${PREVIOUS_TAG}" >&2
    cp "${DEPLOY_DIR}/.env.previous" "${DEPLOY_DIR}/.env"
    export IMAGE_TAG="${PREVIOUS_TAG}"
    docker compose --project-directory "${DEPLOY_DIR}" --env-file "${DEPLOY_DIR}/.env" \
      -f "${COMPOSE_FILE}" up -d --remove-orphans --wait --wait-timeout 180 || true
  fi
  exit "${exit_code}"
}
trap rollback ERR

install -d -m 0750 -o root -g docker "${DEPLOY_DIR}"
install -m 0640 -o root -g docker /tmp/docker-compose.prod.yml "${COMPOSE_FILE}"
gcloud secrets versions access latest --secret "${SECRET_NAME}" --project "${PROJECT_ID}" \
  > "${DEPLOY_DIR}/.env.next"
sed -i -E '/^(DOMAIN_NAME|SITE_SCHEME)=/d' "${DEPLOY_DIR}/.env.next"
printf '\nDOMAIN_NAME=%s\nSITE_SCHEME=%s\n' "${DOMAIN_NAME}" "${SITE_SCHEME}" \
  >> "${DEPLOY_DIR}/.env.next"
chmod 0640 "${DEPLOY_DIR}/.env.next"
chown root:docker "${DEPLOY_DIR}/.env.next"
grep -q '^POSTGRES_PASSWORD=' "${DEPLOY_DIR}/.env.next" || { echo 'Secret lacks POSTGRES_PASSWORD'; exit 1; }
grep -q '^DOMAIN_NAME=' "${DEPLOY_DIR}/.env.next" || { echo 'Secret lacks DOMAIN_NAME'; exit 1; }

AR_HOST="${REGION}-docker.pkg.dev"
ACCESS_TOKEN="$(gcloud auth print-access-token)"
printf '%s' "${ACCESS_TOKEN}" | docker login -u oauth2accesstoken --password-stdin "https://${AR_HOST}"
export IMAGE_PREFIX="${AR_HOST}/${PROJECT_ID}/${REPOSITORY}" IMAGE_TAG="${TAG}"
[[ -f "${DEPLOY_DIR}/current-tag" ]] && PREVIOUS_TAG="$(cat "${DEPLOY_DIR}/current-tag")"
[[ -f "${DEPLOY_DIR}/.env" ]] && cp "${DEPLOY_DIR}/.env" "${DEPLOY_DIR}/.env.previous"
cp "${DEPLOY_DIR}/.env.next" "${DEPLOY_DIR}/.env"
docker compose --project-directory "${DEPLOY_DIR}" --env-file "${DEPLOY_DIR}/.env" \
  -f "${COMPOSE_FILE}" pull
docker compose --project-directory "${DEPLOY_DIR}" --env-file "${DEPLOY_DIR}/.env" \
  -f "${COMPOSE_FILE}" up -d --remove-orphans --wait --wait-timeout 180
printf '%s\n' "${TAG}" > "${DEPLOY_DIR}/current-tag"
docker image prune -f --filter 'until=168h'
rm -f "${DEPLOY_DIR}/.env.next"
docker compose --project-directory "${DEPLOY_DIR}" --env-file "${DEPLOY_DIR}/.env" \
  -f "${COMPOSE_FILE}" ps
trap - ERR
