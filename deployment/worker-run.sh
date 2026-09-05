#!/usr/bin/env bash
set -euo pipefail

DEPLOYMENT_DIR=${VERIDRA_DEPLOYMENT_DIR:-/opt/veridra/deployment}
ENV_FILE=${VERIDRA_DEPLOYMENT_ENV_FILE:-${DEPLOYMENT_DIR}/veridra.env}
LOCK_FILE=${VERIDRA_WORKER_LOCK_FILE:-/run/lock/veridra-worker.lock}

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "VERIDRA monitoring worker already running; skipping overlap."
  exit 0
fi

cd "${DEPLOYMENT_DIR}"
exec docker compose --env-file "${ENV_FILE}" -f compose.yaml run --rm worker
