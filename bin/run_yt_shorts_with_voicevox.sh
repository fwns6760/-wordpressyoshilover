#!/usr/bin/env bash
set -euo pipefail

if [[ "${YT_SHORTS_EMBEDDED_VOICEVOX:-1}" != "1" ]]; then
  exec python3 -m src.yt_shorts_gen "$@"
fi

vv_port="${VV_PORT:-50021}"
vv_host="${VV_HOST:-127.0.0.1}"
export VOICEVOX_BASE_URL="${VOICEVOX_BASE_URL:-http://${vv_host}:${vv_port}}"

if command -v gosu >/dev/null 2>&1 && id user >/dev/null 2>&1; then
  gosu user /opt/voicevox_engine/run \
    --host "${vv_host}" \
    --port "${vv_port}" \
    --disable_mutable_api &
else
  /opt/voicevox_engine/run \
    --host "${vv_host}" \
    --port "${vv_port}" \
    --disable_mutable_api &
fi
voicevox_pid="$!"

cleanup() {
  if kill -0 "${voicevox_pid}" >/dev/null 2>&1; then
    kill "${voicevox_pid}" >/dev/null 2>&1 || true
    wait "${voicevox_pid}" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

python3 - <<'PY'
import os
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

base = os.environ["VOICEVOX_BASE_URL"].rstrip("/")
deadline = time.time() + float(os.environ.get("YT_SHORTS_VOICEVOX_STARTUP_TIMEOUT", "180"))
last_error = None
while time.time() < deadline:
    for endpoint in ("/version", "/speakers"):
        try:
            with urlopen(base + endpoint, timeout=3) as response:
                if 200 <= response.status < 500:
                    sys.exit(0)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    time.sleep(2)
raise SystemExit(f"VOICEVOX did not become ready: {last_error!r}")
PY

python3 -m src.yt_shorts_gen "$@"
