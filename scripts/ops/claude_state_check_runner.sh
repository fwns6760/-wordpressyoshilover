#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${YOSHILOVER_REPO_DIR:-/home/fwns6/code/wordpressyoshilover}"
PROMPT_PATH="${CLAUDE_STATE_CHECK_PROMPT:-prompts/ops/claude_state_check_prompt.md}"
LOG_DIR="${CLAUDE_STATE_CHECK_LOG_DIR:-logs/ops/claude_state_check}"
LOCK_DIR="${CLAUDE_STATE_CHECK_LOCK_DIR:-/tmp/yoshilover_claude_state_check.lock}"
TIMEOUT_SECONDS="${CLAUDE_STATE_CHECK_TIMEOUT_SECONDS:-1200}"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
CLAUDE_PERMISSION_MODE="${CLAUDE_PERMISSION_MODE:-plan}"
CLAUDE_MAX_BUDGET_USD="${CLAUDE_MAX_BUDGET_USD:-0.50}"
MODE="dry-run"

usage() {
  cat <<'USAGE'
Usage:
  claude_state_check_runner.sh [--dry-run|--run|--self-test]

Default: --dry-run

Modes:
  --dry-run    Verify prerequisites, write log, do not invoke Claude CLI.
  --run        Invoke Claude CLI non-interactively with the fixed prompt.
  --self-test  Verify paths/tools and exit without invoking Claude.
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) MODE="dry-run" ;;
    --run) MODE="run" ;;
    --self-test) MODE="self-test" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 64 ;;
  esac
  shift
done

if [[ ! -d "$REPO_DIR" ]]; then
  echo "repo not found: $REPO_DIR" >&2
  exit 66
fi

cd "$REPO_DIR"

mkdir -p "$LOG_DIR"
timestamp="$(date +%Y-%m-%d_%H%M%S)"
log_path="$LOG_DIR/${timestamp}.log"
latest_path="$LOG_DIR/latest.log"
index_path="$LOG_DIR/index.tsv"

log() {
  printf '%s %s\n' "$(date -Is)" "$*" | tee -a "$log_path"
}

finish() {
  local exit_code="$?"
  log "exit_code=${exit_code}"
  printf '%s\t%s\t%s\n' "$(date -Is)" "$MODE" "$exit_code" >> "$index_path"
  ln -sfn "$(basename "$log_path")" "$latest_path"
  if [[ -d "$LOCK_DIR" ]]; then
    rm -rf "$LOCK_DIR"
  fi
  exit "$exit_code"
}
trap finish EXIT

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  mkdir -p "$LOG_DIR"
  {
    printf '%s lock_busy lock=%s\n' "$(date -Is)" "$LOCK_DIR"
    if [[ -f "$LOCK_DIR/pid" ]]; then
      printf 'existing_pid=%s\n' "$(cat "$LOCK_DIR/pid" 2>/dev/null || true)"
    fi
  } | tee -a "$log_path"
  exit 75
fi
printf '%s\n' "$$" > "$LOCK_DIR/pid"

log "mode=${MODE}"
log "repo=${REPO_DIR}"
log "prompt=${PROMPT_PATH}"
log "timeout_seconds=${TIMEOUT_SECONDS}"

required_files=(
  "docs/ops/POLICY.md"
  "docs/ops/CURRENT_STATE.md"
  "docs/ops/OPS_BOARD.yaml"
  "docs/ops/NEXT_SESSION_RUNBOOK.md"
  "docs/ops/WORKER_POOL.md"
  "$PROMPT_PATH"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    log "missing_required_file=${file}"
    exit 66
  fi
done

if ! command -v git >/dev/null 2>&1; then
  log "missing_command=git"
  exit 69
fi
if ! command -v "$CLAUDE_BIN" >/dev/null 2>&1; then
  log "missing_command=${CLAUDE_BIN}"
  exit 69
fi
if ! command -v gcloud >/dev/null 2>&1; then
  log "missing_command=gcloud"
  exit 69
fi
if ! command -v timeout >/dev/null 2>&1; then
  log "missing_command=timeout"
  exit 69
fi

log "git_head=$(git rev-parse --short HEAD)"
log "git_branch=$(git branch --show-current || true)"
log "git_status_begin"
git status --short | sed -n '1,120p' | tee -a "$log_path"
log "git_status_end"

log "prompt_sha256=$(sha256sum "$PROMPT_PATH" | awk '{print $1}')"

if [[ "$MODE" == "self-test" ]]; then
  log "self_test=pass"
  exit 0
fi

if [[ "$MODE" == "dry-run" ]]; then
  log "dry_run=pass"
  log "claude_invocation=skipped"
  log "would_run=${CLAUDE_BIN} -p --permission-mode ${CLAUDE_PERMISSION_MODE} --max-budget-usd ${CLAUDE_MAX_BUDGET_USD} --add-dir ${REPO_DIR} <prompt>"
  exit 0
fi

runtime_prompt="$(mktemp)"
{
  cat "$PROMPT_PATH"
  printf '\n\n## Runner context\n'
  printf -- '- repo: %s\n' "$REPO_DIR"
  printf -- '- mode: run\n'
  printf -- '- generated_at: %s\n' "$(date -Is)"
  printf -- '- hard constraint: read-only/dry-run style state check only unless an action is already classified CLAUDE_AUTO_GO in docs/ops/POLICY.md.\n'
  printf -- '- hard constraint: do not change flags/env/Scheduler/SEO/source/Gemini/mail/publish criteria.\n'
} > "$runtime_prompt"

log "claude_invocation=start"
set +e
timeout "$TIMEOUT_SECONDS" "$CLAUDE_BIN" -p \
  --permission-mode "$CLAUDE_PERMISSION_MODE" \
  --max-budget-usd "$CLAUDE_MAX_BUDGET_USD" \
  --add-dir "$REPO_DIR" \
  < "$runtime_prompt" 2>&1 | tee -a "$log_path"
claude_status="${PIPESTATUS[0]}"
set -e
rm -f "$runtime_prompt"
log "claude_invocation_exit=${claude_status}"
if [[ "$claude_status" == "0" ]]; then
  log "claude_invocation=executed"
fi
exit "$claude_status"
