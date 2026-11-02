#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts
.venv/bin/python scripts/check-boundaries.py
.venv/bin/ruff check apps/api packages tests/api tests/mail_adapters evals infrastructure/migrations scripts/start-live-model.py scripts/smoke-live-model.py
.venv/bin/ruff format --check apps/api packages tests/api tests/mail_adapters evals infrastructure/migrations scripts/start-live-model.py scripts/smoke-live-model.py
.venv/bin/alembic upgrade head
.venv/bin/alembic check
.venv/bin/python -m apps.api.publishing.bootstrap
.venv/bin/pytest -q --junitxml=artifacts/pytest.xml
npm run lint
npm run typecheck
docker compose build web
# Browser regression must not consume a real model account from a live dev server.
.venv/bin/python - <<'CHECK_MODEL'
import os
import httpx
with httpx.Client(trust_env=False, timeout=10) as client:
    response = client.get(os.environ.get("E2E_BASE_URL", "http://127.0.0.1:3100").rstrip("/") + "/api/health")
    response.raise_for_status()
    if response.json().get("editorial_model", {}).get("provider") != "mock":
        raise SystemExit("Browser regression requires an isolated Mock server; start the default local stack first. No live regression calls were made.")
CHECK_MODEL
npm run test:e2e
