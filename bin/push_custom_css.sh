#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CSS_FILE="${YOSHI_CUSTOM_CSS_FILE:-$ROOT_DIR/src/custom.css}"
WP_BASE_URL="${WP_URL:-}"
WP_USER_NAME="${WP_USER:-}"
WP_APP_PASSWORD_VALUE="${WP_APP_PASSWORD:-}"
ENDPOINT="${YOSHI_CUSTOM_CSS_ENDPOINT:-}"
MARKER="${YOSHI_CUSTOM_CSS_MARKER:-}"

if [[ ! -f "$CSS_FILE" ]]; then
  echo "CSS file not found: $CSS_FILE" >&2
  exit 1
fi

if [[ -z "$WP_BASE_URL" || -z "$WP_USER_NAME" || -z "$WP_APP_PASSWORD_VALUE" ]]; then
  echo "WP_URL, WP_USER, and WP_APP_PASSWORD must be set in the environment." >&2
  exit 1
fi

if [[ -z "$ENDPOINT" ]]; then
  ENDPOINT="${WP_BASE_URL%/}/wp-json/yoshilover-063/v1/admin"
fi

if [[ -z "$MARKER" ]]; then
  MARKER="$(grep -m1 '追加CSS' "$CSS_FILE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
fi

if [[ -z "$MARKER" ]]; then
  MARKER="$(grep -m1 'YOSHILOVER' "$CSS_FILE" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
fi

if [[ -z "$MARKER" ]]; then
  echo "Could not derive a custom.css marker from $CSS_FILE." >&2
  exit 1
fi

response_file="$(mktemp)"
cleanup() {
  rm -f "$response_file"
}
trap cleanup EXIT

http_status="$(
  curl -sS \
    -o "$response_file" \
    -w "%{http_code}" \
    -u "$WP_USER_NAME:$WP_APP_PASSWORD_VALUE" \
    -X POST \
    "$ENDPOINT" \
    -H "Accept: application/json" \
    --data-urlencode "action=update_custom_css" \
    --data-urlencode "marker=$MARKER" \
    --data-urlencode "css@$CSS_FILE"
)"

echo "endpoint: $ENDPOINT"
echo "css_file: $CSS_FILE"
echo "marker: $MARKER"
echo "http_status: $http_status"
cat "$response_file"
printf '\n'

if [[ "$http_status" != "200" ]]; then
  echo "Custom CSS push failed with HTTP $http_status." >&2
  exit 1
fi

if ! grep -q '"css_post_id"' "$response_file"; then
  echo "Response did not include css_post_id." >&2
  exit 1
fi

if ! grep -q '"contains_marker":[[:space:]]*true' "$response_file"; then
  echo "Response did not confirm contains_marker=true." >&2
  exit 1
fi
