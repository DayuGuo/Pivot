#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose up -d --build --wait
printf '\nPublishing OS: http://localhost:3100\nAPI: http://localhost:8100/docs\nMailpit (local capture only): http://localhost:8025\n'
