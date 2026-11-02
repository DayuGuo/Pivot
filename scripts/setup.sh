#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/publishing-uv}" uv sync --frozen
npm ci
npx playwright install chromium
