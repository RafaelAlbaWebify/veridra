#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=${VERIDRA_REPO_ROOT:-/opt/veridra}
DEPLOYMENT_DIR=${REPO_ROOT}/deployment
ENV_FILE=${DEPLOYMENT_DIR}/veridra.env
EVIDENCE_DIR=${VERIDRA_EVIDENCE_DIR:-${REPO_ROOT}/artifacts/production}

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}." >&2
  exit 1
fi

# Load runtime values but never print the environment file or secret values.
set -a
# shellcheck disable=SC1090
source "${ENV_FILE}"
set +a

: "${VERIDRA_DOMAIN:?VERIDRA_DOMAIN is required}"
origin="https://${VERIDRA_DOMAIN}"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "${EVIDENCE_DIR}"
out="${EVIDENCE_DIR}/host-${stamp}.txt"

{
  echo "captured_at=${stamp}"
  echo "git_commit=$(git -C "${REPO_ROOT}" rev-parse HEAD)"
  echo "kernel=$(uname -srmo)"
  echo "docker=$(docker --version)"
  echo "compose=$(docker compose version)"
  echo "origin=${origin}"
  echo "--- compose ps ---"
  docker compose --env-file "${ENV_FILE}" -f "${DEPLOYMENT_DIR}/compose.yaml" ps
  echo "--- worker timer ---"
  systemctl is-enabled veridra-worker.timer
  systemctl is-active veridra-worker.timer
  systemctl list-timers --all veridra-worker.timer --no-pager
  echo "--- backup timer ---"
  systemctl is-enabled veridra-backup.timer
  systemctl is-active veridra-backup.timer
  systemctl list-timers --all veridra-backup.timer --no-pager
  echo "--- public health ---"
  curl --fail --silent --show-error --max-time 15 "${origin}/health/live"
  echo
  curl --fail --silent --show-error --max-time 15 "${origin}/health/ready"
  echo
} >"${out}"

chmod 600 "${out}"
echo "evidence=${out}"
