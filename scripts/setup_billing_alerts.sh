#!/usr/bin/env bash

set -euo pipefail

PROJECT_ID="${PROJECT_ID:-baseballsite}"
EXPECTED_CURRENCY="${EXPECTED_CURRENCY:-JPY}"
NOTIFICATION_CHANNEL_ID="${NOTIFICATION_CHANNEL_ID:-7008520332246366374}"
NOTIFICATION_CHANNEL="projects/${PROJECT_ID}/notificationChannels/${NOTIFICATION_CHANNEL_ID}"
PROJECT_FILTER_INPUT="projects/${PROJECT_ID}"
EXPECTED_PROJECT_FILTER=""

BUDGET_NAMES=(
  "yoshilover-budget-warn"
  "yoshilover-budget-investigate"
  "yoshilover-budget-emergency"
)

BUDGET_AMOUNTS=(
  "1500JPY"
  "4500JPY"
  "7500JPY"
)

THRESHOLDS=(
  "0.5"
  "0.9"
  "1.0"
)

log() {
  printf '[billing-alerts] %s\n' "$*"
}

fail() {
  printf '[billing-alerts] ERROR: %s\n' "$*" >&2
  exit 1
}

mask_billing_account() {
  local raw="$1"
  local len=${#raw}
  if (( len <= 8 )); then
    printf '%s' "$raw"
    return
  fi
  printf '%s****%s' "${raw:0:4}" "${raw:len-4:4}"
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "Required command not found: $1"
}

ensure_expected_currency() {
  local billing_account_id="$1"
  local currency_code

  currency_code="$(
    gcloud billing accounts describe "$billing_account_id" \
      --format='value(currencyCode)' \
      2>/dev/null | head -n1
  )"

  [[ -n "$currency_code" ]] || fail "Unable to determine billing account currency"
  if [[ "$currency_code" != "$EXPECTED_CURRENCY" ]]; then
    fail "Linked billing account currency is ${currency_code}; ticket 167 v2 requires ${EXPECTED_CURRENCY} budgets and was not applied"
  fi

  log "Verified billing account currency ${currency_code}"
}

detect_billing_account_id() {
  if [[ -n "${BILLING_ACCOUNT_ID:-}" ]]; then
    printf '%s' "$BILLING_ACCOUNT_ID"
    return
  fi

  local linked_account
  linked_account="$(
    gcloud billing projects describe "$PROJECT_ID" \
      --format='value(billingAccountName)' \
      2>/dev/null | head -n1 | sed 's|billingAccounts/||'
  )"

  [[ -n "$linked_account" ]] || fail "Unable to resolve billing account from project ${PROJECT_ID}"
  printf '%s' "$linked_account"
}

resolve_project_filter() {
  local project_number

  project_number="$(
    gcloud projects describe "$PROJECT_ID" \
      --format='value(projectNumber)' \
      2>/dev/null | head -n1
  )"

  [[ -n "$project_number" ]] || fail "Unable to resolve project number for ${PROJECT_ID}"
  printf 'projects/%s' "$project_number"
}

ensure_notification_channel() {
  local channel_csv
  local channel_name
  local channel_type
  local channel_enabled
  local channel_email

  channel_csv="$(
    gcloud alpha monitoring channels describe "$NOTIFICATION_CHANNEL" \
      --format='csv[no-heading](name,type,enabled,labels.email_address)' \
      2>/dev/null
  )"

  [[ -n "$channel_csv" ]] || fail "Unable to describe notification channel ${NOTIFICATION_CHANNEL_ID}"

  IFS=',' read -r channel_name channel_type channel_enabled channel_email <<<"$channel_csv"

  [[ "$channel_name" == "$NOTIFICATION_CHANNEL" ]] || fail "Notification channel resource mismatch"
  [[ "$channel_type" == "email" ]] || fail "Notification channel ${NOTIFICATION_CHANNEL_ID} is not an email channel"
  [[ "$channel_enabled" == "True" || "$channel_enabled" == "true" ]] || fail "Notification channel ${NOTIFICATION_CHANNEL_ID} is not enabled"
  [[ "$channel_email" == *"@"* ]] || fail "Notification channel ${NOTIFICATION_CHANNEL_ID} does not expose an email recipient"

  log "Verified monitoring email channel ${NOTIFICATION_CHANNEL_ID}"
}

budget_resource_name() {
  local billing_account_id="$1"
  local display_name="$2"

  gcloud billing budgets list \
    --billing-account="$billing_account_id" \
    --filter="displayName=${display_name}" \
    --format='value(name)' \
    2>/dev/null
}

budget_exists() {
  local billing_account_id="$1"
  local display_name="$2"

  [[ -n "$(budget_resource_name "$billing_account_id" "$display_name")" ]]
}

verify_budget_shape() {
  local billing_account_id="$1"
  local display_name="$2"
  local expected_amount="$3"
  local -a budget_names=()
  local budget_name
  local amount_units
  local amount_currency
  local thresholds
  local monitoring_channel
  local project_filter
  local expected_units
  local budget_count

  mapfile -t budget_names < <(budget_resource_name "$billing_account_id" "$display_name")
  budget_count="${#budget_names[@]}"
  if (( budget_count == 0 )); then
    fail "Budget ${display_name} was not found"
  fi
  if (( budget_count > 1 )); then
    fail "Multiple budgets share display name ${display_name}; resolve the collision before rerunning ticket 167 v2"
  fi

  budget_name="${budget_names[0]}"
  expected_units="${expected_amount%${EXPECTED_CURRENCY}}"

  amount_units="$(
    gcloud billing budgets list \
      --billing-account="$billing_account_id" \
      --filter="name=${budget_name}" \
      --format='value(amount.specifiedAmount.units)' \
      2>/dev/null | head -n1
  )"
  amount_currency="$(
    gcloud billing budgets list \
      --billing-account="$billing_account_id" \
      --filter="name=${budget_name}" \
      --format='value(amount.specifiedAmount.currencyCode)' \
      2>/dev/null | head -n1
  )"
  thresholds="$(
    gcloud billing budgets list \
      --billing-account="$billing_account_id" \
      --filter="name=${budget_name}" \
      --format='value(thresholdRules.thresholdPercent)' \
      2>/dev/null | tr ';' ',' | tr -d '[:space:]'
  )"
  monitoring_channel="$(
    gcloud billing budgets list \
      --billing-account="$billing_account_id" \
      --filter="name=${budget_name}" \
      --format='value(notificationsRule.monitoringNotificationChannels)' \
      2>/dev/null | tr ';' '\n' | head -n1
  )"
  project_filter="$(
    gcloud billing budgets list \
      --billing-account="$billing_account_id" \
      --filter="name=${budget_name}" \
      --format='value(budgetFilter.projects)' \
      2>/dev/null | tr ';' '\n' | head -n1
  )"

  [[ "$amount_units" == "$expected_units" ]] || fail "Budget amount verification failed for ${display_name}"
  [[ "$amount_currency" == "$EXPECTED_CURRENCY" ]] || fail "Budget currency verification failed for ${display_name}"
  [[ "$thresholds" == "0.5,0.9,1.0" ]] || fail "Threshold verification failed for ${display_name}"
  [[ "$monitoring_channel" == "$NOTIFICATION_CHANNEL" ]] || fail "Notification channel verification failed for ${display_name}"
  [[ "$project_filter" == "$EXPECTED_PROJECT_FILTER" ]] || fail "Project filter verification failed for ${display_name}"

  log "Verified ${display_name}: amount, currency, thresholds, channel, and project scope are correct"
}

create_budget() {
  local billing_account_id="$1"
  local display_name="$2"
  local amount="$3"

  if budget_exists "$billing_account_id" "$display_name"; then
    verify_budget_shape "$billing_account_id" "$display_name" "$amount"
    log "Budget already present; keeping ${display_name}"
    return
  fi

  gcloud billing budgets create \
    --billing-account="$billing_account_id" \
    --display-name="$display_name" \
    --budget-amount="$amount" \
    --calendar-period=month \
    --filter-projects="$PROJECT_FILTER_INPUT" \
    --notifications-rule-monitoring-notification-channels="$NOTIFICATION_CHANNEL" \
    --threshold-rule="percent=${THRESHOLDS[0]}" \
    --threshold-rule="percent=${THRESHOLDS[1]}" \
    --threshold-rule="percent=${THRESHOLDS[2]}" \
    --format='value(name)' \
    --quiet >/dev/null

  log "Created budget ${display_name}"
}

main() {
  require_command gcloud

  local billing_account_id
  billing_account_id="$(detect_billing_account_id)"
  EXPECTED_PROJECT_FILTER="$(resolve_project_filter)"

  log "Using billing account $(mask_billing_account "$billing_account_id")"

  ensure_expected_currency "$billing_account_id"
  ensure_notification_channel

  local i
  for i in "${!BUDGET_NAMES[@]}"; do
    create_budget "$billing_account_id" "${BUDGET_NAMES[$i]}" "${BUDGET_AMOUNTS[$i]}"
  done

  for i in "${!BUDGET_NAMES[@]}"; do
    verify_budget_shape "$billing_account_id" "${BUDGET_NAMES[$i]}" "${BUDGET_AMOUNTS[$i]}"
  done

  log "Billing alert setup completed"
}

main "$@"
