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
install -m 0755 "${DEPLOYMENT_DIR}/worker-run.sh" /opt/veridra/deployment/worker-run.sh
install -m 0755 "${DEPLOYMENT_DIR}/backup-run.sh" /opt/veridra/deployment/backup-run.sh
install -m 0644 "${DEPLOYMENT_DIR}/systemd/veridra-worker.service" /etc/systemd/system/veridra-worker.service
install -m 0644 "${DEPLOYMENT_DIR}/systemd/veridra-worker.timer" /etc/systemd/system/veridra-worker.timer
install -m 0644 "${DEPLOYMENT_DIR}/systemd/veridra-backup.service" /etc/systemd/system/veridra-backup.service
install -m 0644 "${DEPLOYMENT_DIR}/systemd/veridra-backup.timer" /etc/systemd/system/veridra-backup.timer

systemctl daemon-reload
systemctl enable --now veridra-worker.timer
systemctl enable --now veridra-backup.timer

systemctl --no-pager --full status veridra-worker.timer veridra-backup.timer || true
