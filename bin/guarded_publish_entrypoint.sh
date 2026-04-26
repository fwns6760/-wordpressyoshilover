#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

GCS_PREFIX="${GCS_PREFIX:-gs://baseballsite-yoshilover-state/guarded_publish}"
LOCAL_TMP="${LOCAL_TMP:-/tmp/pub004d}"
CRON_EVAL_PATH="${LOCAL_TMP}/cron_eval.json"
HISTORY_PATH="${LOCAL_TMP}/guarded_publish_history.jsonl"
YELLOW_LOG_PATH="${LOCAL_TMP}/guarded_publish_yellow_log.jsonl"
CLEANUP_LOG_PATH="${LOCAL_TMP}/guarded_publish_cleanup_log.jsonl"
BACKUP_DIR="${LOCAL_TMP}/cleanup_backup"

mkdir -p "${LOCAL_TMP}" "${BACKUP_DIR}"
cd "${REPO_ROOT}"

download_optional_file() {
  local remote_path="$1"
  local local_path="$2"
  local output=""

  if output="$(gcloud storage cp "${remote_path}" "${local_path}" 2>&1)"; then
    return 0
  fi

  if printf '%s' "${output}" | grep -Eqi 'No URLs matched|matched no objects|does not exist'; then
    : > "${local_path}"
    return 0
  fi

  printf '%s\n' "${output}" >&2
  return 1
}

upload_file() {
  local local_path="$1"
  local remote_path="$2"

  if [[ -f "${local_path}" ]]; then
    gcloud storage cp "${local_path}" "${remote_path}" >/dev/null
  fi
}

download_optional_file "${GCS_PREFIX}/guarded_publish_history.jsonl" "${HISTORY_PATH}"
download_optional_file "${GCS_PREFIX}/guarded_publish_yellow_log.jsonl" "${YELLOW_LOG_PATH}"
download_optional_file "${GCS_PREFIX}/guarded_publish_cleanup_log.jsonl" "${CLEANUP_LOG_PATH}"

python3 -m src.tools.run_guarded_publish_evaluator \
  --window-hours 999999 \
  --max-pool 500 \
  --format json \
  --output "${CRON_EVAL_PATH}" \
  --exclude-published-today

python3 -m src.tools.run_guarded_publish \
  --input-from "${CRON_EVAL_PATH}" \
  --max-burst 20 \
  --live \
  --daily-cap-allow \
  --backup-dir "${BACKUP_DIR}" \
  --history-path "${HISTORY_PATH}" \
  --yellow-log-path "${YELLOW_LOG_PATH}" \
  --cleanup-log-path "${CLEANUP_LOG_PATH}"

upload_file "${HISTORY_PATH}" "${GCS_PREFIX}/guarded_publish_history.jsonl"
upload_file "${YELLOW_LOG_PATH}" "${GCS_PREFIX}/guarded_publish_yellow_log.jsonl"
upload_file "${CLEANUP_LOG_PATH}" "${GCS_PREFIX}/guarded_publish_cleanup_log.jsonl"

if find "${BACKUP_DIR}" -mindepth 1 -print -quit | grep -q .; then
  gcloud storage cp --recursive "${BACKUP_DIR}" "${GCS_PREFIX}/" >/dev/null
fi
