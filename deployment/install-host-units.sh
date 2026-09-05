#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run as root so systemd units can be installed." >&2
  exit 1
fi

REPO_ROOT=${VERIDRA_REPO_ROOT:-/opt/veridra}
DEPLOYMENT_DIR=${REPO_ROOT}/deployment
ENV_FILE=${DEPLOYMENT_DIR}/veridra.env

for command in docker systemctl flock; do
  if ! command -v "${command}" >/dev/null 2>&1; then
    echo "Missing required host command: ${command}" >&2
    exit 1
  fi
done

docker compose version >/dev/null

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}; copy and populate veridra.env.example first." >&2
  exit 1
fi

chmod 600 "${ENV_FILE}"
install -d -m 0700 /opt/veridra-backups
install -d -m 0700 /etc/veridra
install -m 0755 "${DEPLOYMENT_DIR}/worker-run.sh" /opt/veridra/deployment/worker-run.sh
install -m 0755 "${DEPLOYMENT_DIR}/backup-run.sh" /opt/veridra/deployment/backup-run.sh
install -m 0755 "${DEPLOYMENT_DIR}/offhost-backup-run.sh" /opt/veridra/deployment/offhost-backup-run.sh
install -m 0644 "${DEPLOYMENT_DIR}/systemd/veridra-worker.service" /etc/systemd/system/veridra-worker.service
install -m 0644 "${DEPLOYMENT_DIR}/systemd/veridra-worker.timer" /etc/systemd/system/veridra-worker.timer
install -m 0644 "${DEPLOYMENT_DIR}/systemd/veridra-backup.service" /etc/systemd/system/veridra-backup.service
install -m 0644 "${DEPLOYMENT_DIR}/systemd/veridra-backup.timer" /etc/systemd/system/veridra-backup.timer
install -m 0644 "${DEPLOYMENT_DIR}/systemd/veridra-offhost-backup.service" /etc/systemd/system/veridra-offhost-backup.service

systemctl daemon-reload
systemctl enable --now veridra-worker.timer
systemctl enable --now veridra-backup.timer

systemctl --no-pager --full status veridra-worker.timer veridra-backup.timer || true
if [[ -f /etc/veridra/offhost-backup.env ]]; then
  if ! command -v restic >/dev/null 2>&1; then
    echo "Off-host backup config exists but restic is not installed." >&2
    exit 1
  fi
  chmod 600 /etc/veridra/offhost-backup.env
  echo "Off-host backup config detected. The service will run after each successful local backup."
else
  echo "Off-host backup is not configured yet; see docs/operations/offhost-backup-provider.md."
fi
