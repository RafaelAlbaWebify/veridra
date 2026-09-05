#!/usr/bin/env bash
set -euo pipefail

DEPLOYMENT_DIR=${VERIDRA_DEPLOYMENT_DIR:-/opt/veridra/deployment}
ENV_FILE=${VERIDRA_DEPLOYMENT_ENV_FILE:-${DEPLOYMENT_DIR}/veridra.env}
BACKUP_DIR=${VERIDRA_BACKUP_DIR:-/opt/veridra-backups}
MAINTENANCE_LOCK=${VERIDRA_MAINTENANCE_LOCK:-/run/lock/veridra-maintenance.lock}
WORKER_TIMER=${VERIDRA_WORKER_TIMER:-veridra-worker.timer}

exec 9>"${MAINTENANCE_LOCK}"
if ! flock -n 9; then
  echo "Another VERIDRA maintenance operation is active; backup aborted."
  exit 1
fi

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"
cd "${DEPLOYMENT_DIR}"

worker_timer_was_active=0
if systemctl is-active --quiet "${WORKER_TIMER}"; then
  worker_timer_was_active=1
  systemctl stop "${WORKER_TIMER}"
fi

restore_services() {
  docker compose --env-file "${ENV_FILE}" -f compose.yaml start web >/dev/null 2>&1 || true
  if [[ "${worker_timer_was_active}" -eq 1 ]]; then
    systemctl start "${WORKER_TIMER}" >/dev/null 2>&1 || true
  fi
}
trap restore_services EXIT

# Ensure a running bounded worker cannot overlap the quiesced snapshot.
systemctl stop veridra-worker.service >/dev/null 2>&1 || true

docker compose --env-file "${ENV_FILE}" -f compose.yaml stop web

stamp=$(date -u +%Y%m%dT%H%M%SZ)
archive="veridra-${stamp}.zip"

docker compose --env-file "${ENV_FILE}" -f compose.yaml run --rm \
  -v "${BACKUP_DIR}:/backups" \
  worker veridra-backup backup \
  --output "/backups/${archive}" \
  --confirm-quiesced

if [[ ! -s "${BACKUP_DIR}/${archive}" ]]; then
  echo "Backup archive missing or empty: ${BACKUP_DIR}/${archive}" >&2
  exit 1
fi

printf 'backup=%s size=%s created_at=%s\n' \
  "${BACKUP_DIR}/${archive}" \
  "$(stat -c %s "${BACKUP_DIR}/${archive}")" \
  "${stamp}"

echo "Copy this verified archive to independent off-host storage; local-only backup is not sufficient."
