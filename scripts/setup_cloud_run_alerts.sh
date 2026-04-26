#!/usr/bin/env bash

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-baseballsite}"
REGION="${REGION:-asia-northeast1}"
ALERT_EMAIL="${ALERT_EMAIL:-fwns6760@gmail.com}"
CHANNEL_DISPLAY_NAME="${CHANNEL_DISPLAY_NAME:-yoshilover cloud run job failure alerts}"
ALIGNMENT_PERIOD="${ALIGNMENT_PERIOD:-300s}"
AUTO_CLOSE="${AUTO_CLOSE:-1800s}"

JOB_NAMES=(
  "draft-body-editor"
  "publish-notice"
)

# Keep the existing two lanes in sync with ticket 166. Future lanes can be added
# here without changing the alerting flow.
declare -A JOB_SCHEDULES=(
  ["draft-body-editor"]="2,12,22,32,42,52 * * * * (Asia/Tokyo)"
  ["publish-notice"]="15 * * * * (Asia/Tokyo)"
)

log() {
  printf '[cloud-run-alerts] %s\n' "$*" >&2
}

fail() {
  printf '[cloud-run-alerts] ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

prepare_gcloud_config() {
  if [[ -n "${CLOUDSDK_CONFIG:-}" ]]; then
    mkdir -p "$CLOUDSDK_CONFIG"
    return
  fi

  export CLOUDSDK_CONFIG=/tmp/gcloud-config
  mkdir -p "$CLOUDSDK_CONFIG"
  if [[ -d "${HOME}/.config/gcloud" && ! -d "${CLOUDSDK_CONFIG}/configurations" ]]; then
    cp -r "${HOME}/.config/gcloud/"* "${CLOUDSDK_CONFIG}/" 2>/dev/null || true
  fi
}

metric_name_for_job() {
  local job_name="$1"
  printf 'cloud_run_job_failure_%s' "${job_name//-/_}"
}

policy_display_name_for_job() {
  local job_name="$1"
  printf 'cron-fail-%s' "$job_name"
}

job_logs_query_url() {
  local job_name="$1"
  printf 'https://console.cloud.google.com/logs/query;query=resource.type%%3D%%22cloud_run_job%%22%%0Aresource.labels.job_name%%3D%%22%s%%22%%0Aseverity%%3E%%3DERROR?project=%s' \
    "$job_name" "$PROJECT_ID"
}

job_recovery_url() {
  local job_name="$1"
  printf 'https://console.cloud.google.com/run/jobs/details/%s/%s/executions?project=%s' \
    "$REGION" "$job_name" "$PROJECT_ID"
}

metric_filter_for_job() {
  local job_name="$1"
  printf 'resource.type="cloud_run_job" AND resource.labels.job_name="%s" AND logName="projects/%s/logs/cloudaudit.googleapis.com%%2Fsystem_event" AND severity>=ERROR' \
    "$job_name" "$PROJECT_ID"
}

find_existing_channel() {
  gcloud alpha monitoring channels list \
    --project="$PROJECT_ID" \
    --format='value(name,type,labels.email_address,verificationStatus)' \
    | awk -F '\t' -v email="$ALERT_EMAIL" '
        $2 == "email" && $3 == email && $4 == "VERIFIED" { print $1; found = 1; exit }
        $2 == "email" && $3 == email && fallback == "" { fallback = $1 }
        END {
          if (!found && fallback != "") {
            print fallback
          }
        }
      '
}

channel_verification_status() {
  local channel_name="$1"
  local status
  status="$(
    gcloud alpha monitoring channels describe "$channel_name" \
      --project="$PROJECT_ID" \
      --format='value(verificationStatus)' 2>/dev/null || true
  )"

  if [[ -n "$status" ]]; then
    printf '%s' "$status"
    return
  fi

  printf 'NOT_RETURNED_BY_API'
}

ensure_notification_channel() {
  local existing_channel
  existing_channel="$(find_existing_channel)"

  if [[ -n "$existing_channel" ]]; then
    log "Reusing notification channel ${existing_channel}"
    printf '%s' "$existing_channel"
    return
  fi

  local created_channel
  created_channel="$(
    gcloud alpha monitoring channels create \
      --project="$PROJECT_ID" \
      --display-name="$CHANNEL_DISPLAY_NAME" \
      --description="Ticket 166 Cloud Run Job failure alerts for ${ALERT_EMAIL}" \
      --type=email \
      --channel-labels="email_address=${ALERT_EMAIL}" \
      --format='value(name)'
  )"

  [[ -n "$created_channel" ]] || fail "Failed to create notification channel for ${ALERT_EMAIL}"
  log "Created notification channel ${created_channel}"
  printf '%s' "$created_channel"
}

ensure_log_metric() {
  local job_name="$1"
  local metric_name
  local metric_filter

  metric_name="$(metric_name_for_job "$job_name")"
  metric_filter="$(metric_filter_for_job "$job_name")"

  if gcloud logging metrics describe "$metric_name" --project="$PROJECT_ID" >/dev/null 2>&1; then
    gcloud logging metrics update "$metric_name" \
      --project="$PROJECT_ID" \
      --description="Count failed Cloud Run Job executions for ${job_name}" \
      --log-filter="$metric_filter" >/dev/null
    log "Updated log metric ${metric_name}"
    return
  fi

  gcloud logging metrics create "$metric_name" \
    --project="$PROJECT_ID" \
    --description="Count failed Cloud Run Job executions for ${job_name}" \
    --log-filter="$metric_filter" >/dev/null
  log "Created log metric ${metric_name}"
}

find_existing_policy() {
  local display_name="$1"
  gcloud alpha monitoring policies list \
    --project="$PROJECT_ID" \
    --format='value(name,displayName)' \
    | awk -F '\t' -v target="$display_name" '$2 == target { print $1; exit }'
}

write_policy_file() {
  local job_name="$1"
  local channel_name="$2"
  local output_path="$3"
  local metric_name
  local display_name
  local logs_url
  local recovery_url
  local schedule

  metric_name="$(metric_name_for_job "$job_name")"
  display_name="$(policy_display_name_for_job "$job_name")"
  logs_url="$(job_logs_query_url "$job_name")"
  recovery_url="$(job_recovery_url "$job_name")"
  schedule="${JOB_SCHEDULES[$job_name]}"

  cat >"$output_path" <<EOF
displayName: ${display_name}
documentation:
  content: |-
    Cloud Run Job failure detected.

    - Job: \`${job_name}\`
    - Expected schedule: \`${schedule}\`
    - Logs: ${logs_url}
    - Recovery: ${recovery_url}
    - Runbook: \`doc/active/166-deployment-notes.md\`
  mimeType: text/markdown
combiner: OR
conditions:
  - displayName: ${job_name} failed executions > 0 in 5m
    conditionThreshold:
      filter: 'metric.type="logging.googleapis.com/user/${metric_name}" AND resource.type="cloud_run_job"'
      aggregations:
        - alignmentPeriod: ${ALIGNMENT_PERIOD}
          perSeriesAligner: ALIGN_DELTA
      comparison: COMPARISON_GT
      thresholdValue: 0
      duration: 0s
      trigger:
        count: 1
notificationChannels:
  - ${channel_name}
alertStrategy:
  autoClose: ${AUTO_CLOSE}
enabled: true
userLabels:
  ticket: "166"
  lane: "a"
  job: "${job_name//-/_}"
EOF
}

ensure_alert_policy() {
  local job_name="$1"
  local channel_name="$2"
  local display_name
  local existing_policy
  local tmp_dir
  local policy_file

  display_name="$(policy_display_name_for_job "$job_name")"
  existing_policy="$(find_existing_policy "$display_name")"
  tmp_dir="$(mktemp -d)"
  policy_file="${tmp_dir}/${job_name}.yaml"

  write_policy_file "$job_name" "$channel_name" "$policy_file"

  if [[ -n "$existing_policy" ]]; then
    gcloud alpha monitoring policies delete "$existing_policy" \
      --project="$PROJECT_ID" \
      --quiet >/dev/null
    log "Deleted existing alert policy ${existing_policy}"
  fi

  local attempt
  local max_attempts=20
  local sleep_seconds=15
  local create_output
  for attempt in $(seq 1 "$max_attempts"); do
    if create_output="$(
      gcloud alpha monitoring policies create \
        --project="$PROJECT_ID" \
        --policy-from-file="$policy_file" 2>&1
    )"; then
      [[ -n "$create_output" ]] && printf '%s\n' "$create_output" >&2
      rm -rf "$tmp_dir"
      log "Created alert policy ${display_name}"
      return
    fi

    if grep -Fq 'Cannot find metric(s) that match type' <<<"$create_output"; then
      log "Metric descriptor for ${job_name} not visible yet (${attempt}/${max_attempts}); retrying in ${sleep_seconds}s"
      sleep "$sleep_seconds"
      continue
    fi

    rm -rf "$tmp_dir"
    printf '%s\n' "$create_output" >&2
    fail "Failed to create alert policy ${display_name}"
  done

  rm -rf "$tmp_dir"
  printf '%s\n' "$create_output" >&2
  fail "Metric descriptor propagation timed out for ${display_name}"
}

verify_log_metric() {
  local job_name="$1"
  local metric_name

  metric_name="$(metric_name_for_job "$job_name")"
  gcloud logging metrics describe "$metric_name" \
    --project="$PROJECT_ID" \
    --format='value(name)' | grep -Fxq "$metric_name" \
    || fail "Log metric verification failed for ${metric_name}"
}

verify_alert_policy() {
  local job_name="$1"
  local display_name

  display_name="$(policy_display_name_for_job "$job_name")"
  gcloud alpha monitoring policies list \
    --project="$PROJECT_ID" \
    --format='value(displayName,enabled)' \
    | awk -F '\t' -v target="$display_name" '$1 == target && $2 == "True" { found = 1 } END { exit(found ? 0 : 1) }' \
    || fail "Alert policy verification failed for ${display_name}"
}

main() {
  require_command gcloud
  prepare_gcloud_config

  gcloud projects describe "$PROJECT_ID" >/dev/null 2>&1 \
    || fail "Unable to access project ${PROJECT_ID}"

  local channel_name
  channel_name="$(ensure_notification_channel)"

  local job_name
  for job_name in "${JOB_NAMES[@]}"; do
    ensure_log_metric "$job_name"
    ensure_alert_policy "$job_name" "$channel_name"
    verify_log_metric "$job_name"
    verify_alert_policy "$job_name"
  done

  local verification_status
  verification_status="$(channel_verification_status "$channel_name")"
  [[ -n "$verification_status" ]] || verification_status="UNKNOWN"

  log "Notification channel verification status: ${verification_status}"
  log "Cloud Run Job failure alert setup completed"
}

main "$@"
