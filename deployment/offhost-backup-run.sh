#!/usr/bin/env bash
set -euo pipefail

CONFIG_FILE=${VERIDRA_OFFHOST_CONFIG:-/etc/veridra/offhost-backup.env}

if [[ ! -f "${CONFIG_FILE}" ]]; then
  echo "Off-host backup config is absent; replication is not configured: ${CONFIG_FILE}" >&2
  exit 2
fi

if [[ $(id -u) -ne 0 ]]; then
  echo "Off-host backup must run as root so production secrets stay root-only." >&2
  exit 1
fi

mode=$(stat -c '%a' "${CONFIG_FILE}")
if (( 10#${mode} > 600 )); then
  echo "Refusing off-host config with permissions broader than 0600: ${CONFIG_FILE} (${mode})" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${CONFIG_FILE}"

required=(
  RESTIC_REPOSITORY
  RESTIC_PASSWORD_FILE
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_DEFAULT_REGION
)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required off-host backup setting: ${name}" >&2
    exit 1
  fi
done

if [[ ! -f "${RESTIC_PASSWORD_FILE}" ]]; then
  echo "Missing restic password file: ${RESTIC_PASSWORD_FILE}" >&2
  exit 1
fi
password_mode=$(stat -c '%a' "${RESTIC_PASSWORD_FILE}")
if (( 10#${password_mode} > 600 )); then
  echo "Refusing restic password file with permissions broader than 0600." >&2
  exit 1
fi

if ! command -v restic >/dev/null 2>&1; then
  echo "restic is not installed or not available in PATH." >&2
  exit 1
fi

BACKUP_DIR=${VERIDRA_BACKUP_DIR:-/opt/veridra-backups}
if [[ ! -d "${BACKUP_DIR}" ]]; then
  echo "Local backup directory does not exist: ${BACKUP_DIR}" >&2
  exit 1
fi

latest=$(find "${BACKUP_DIR}" -maxdepth 1 -type f -name 'veridra-*.zip' -printf '%T@ %p\n' \
  | sort -nr \
  | head -n1 \
  | cut -d' ' -f2-)
if [[ -z "${latest}" || ! -s "${latest}" ]]; then
  echo "No non-empty verified VERIDRA application archive is available for replication." >&2
  exit 1
fi

export RESTIC_REPOSITORY RESTIC_PASSWORD_FILE AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION

# A readable repository is an explicit prerequisite. Initialization is a controlled one-time
# operator action so a typo cannot silently create a new empty repository in production.
if ! restic snapshots --latest 1 >/dev/null 2>&1; then
  echo "Configured restic repository is not initialized/readable; initialize and verify it explicitly first." >&2
  exit 1
fi

archive_name=$(basename "${latest}")
archive_size=$(stat -c '%s' "${latest}")
archive_sha256=$(sha256sum "${latest}" | awk '{print $1}')

restic backup \
  --host "$(hostname -s)" \
  --tag veridra-application-archive \
  -- "${latest}"

snapshot_id=$(restic snapshots \
  --latest 1 \
  --host "$(hostname -s)" \
  --tag veridra-application-archive \
  --json \
  | python3 -c 'import json,sys; rows=json.load(sys.stdin); print(rows[-1]["short_id"] if rows else "")')

if [[ -z "${snapshot_id}" ]]; then
  echo "Remote backup completed but a matching restic snapshot could not be confirmed." >&2
  exit 1
fi

printf 'offhost_backup=%s size=%s sha256=%s snapshot=%s\n' \
  "${archive_name}" \
  "${archive_size}" \
  "${archive_sha256}" \
  "${snapshot_id}"
