#!/usr/bin/env bash
set -euo pipefail

LOCK_FILE=${VERIDRA_WORKER_LOCK_FILE:-/run/lock/veridra-monitoring-worker.lock}
COMPOSE_FILE=${VERIDRA_COMPOSE_FILE:-/opt/veridra/deploy/vm/docker-compose.yml}
ENV_FILE=${VERIDRA_COMPOSE_ENV_FILE:-/etc/veridra/compose.env}

exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
  echo "VERIDRA monitoring worker already running; skipping overlapping invocation."
  exit 0
fi

exec docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}" run --rm worker
