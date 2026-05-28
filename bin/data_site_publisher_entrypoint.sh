#!/usr/bin/env bash
set -euo pipefail

cd /app

exec python3 -m src.data_site_publisher "$@"
