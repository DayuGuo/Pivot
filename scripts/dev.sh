#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
[[ -x .venv/bin/python && -d node_modules ]] || ./scripts/setup.sh
docker compose up -d db mailpit --wait
.venv/bin/alembic upgrade head
.venv/bin/python -m apps.api.publishing.bootstrap
setsid .venv/bin/uvicorn apps.api.publishing.main:app --host 127.0.0.1 --port 8100 &
api_pid=$!
trap 'kill -- "-$api_pid" "-${web_pid:-0}" 2>/dev/null || true' EXIT INT TERM
setsid npm run dev -- --port 3100 &
web_pid=$!
wait -n "$api_pid" "$web_pid"
