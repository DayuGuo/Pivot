#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts
# Refuse before DB writes/builds when the selected running Compose API is live.
# This reads only the provider name; never dumps configuration or credentials.
docker compose exec -T api python -c 'import os; import sys; sys.exit(0 if os.environ.get("EDITORIAL_MODEL_PROVIDER", "mock") == "mock" else "Verification requires an isolated Mock Compose API; live service left unchanged.")'
.venv/bin/python - <<'CHECK_TARGET'
import os
import httpx
with httpx.Client(trust_env=False, timeout=10) as client:
    response = client.get(os.environ.get("E2E_BASE_URL", "http://127.0.0.1:3100").rstrip("/") + "/api/health")
    response.raise_for_status()
    if response.json().get("editorial_model", {}).get("provider") != "mock":
        raise SystemExit("Verification target must be Mock; live service left unchanged.")
CHECK_TARGET
.venv/bin/python scripts/check-research-library.py
.venv/bin/python scripts/check-boundaries.py
.venv/bin/ruff check scripts/accept-revision-comparison.py
.venv/bin/ruff format --check scripts/accept-revision-comparison.py
.venv/bin/python scripts/accept-revision-comparison.py > artifacts/revision-protocol-mock.json
.venv/bin/ruff check --no-cache scripts/start-local.py scripts/accept-live-publishing.py scripts/accept-dossier-model.py scripts/accept-document-import.py scripts/evaluate-public-papers.py scripts/evaluate-evidence-integrity.py scripts/build-vps-app.py scripts/accept-vps-preview.py scripts/accept-vps-concurrency.py infrastructure/vps
.venv/bin/ruff format --check --no-cache scripts/start-local.py scripts/accept-live-publishing.py scripts/accept-dossier-model.py scripts/accept-document-import.py scripts/evaluate-public-papers.py scripts/evaluate-evidence-integrity.py scripts/build-vps-app.py scripts/accept-vps-preview.py scripts/accept-vps-concurrency.py infrastructure/vps
.venv/bin/ruff check --no-cache apps/api packages tests/api tests/mail_adapters evals infrastructure/migrations scripts/start-live-model.py scripts/smoke-live-model.py scripts/accept-live-model.py scripts/check-research-library.py scripts/rehearse-publishing-migration.py
.venv/bin/ruff format --check --no-cache apps/api packages tests/api tests/mail_adapters evals infrastructure/migrations scripts/start-live-model.py scripts/smoke-live-model.py scripts/accept-live-model.py scripts/check-research-library.py scripts/rehearse-publishing-migration.py
.venv/bin/python scripts/evaluate-evidence-integrity.py --report artifacts/evidence-offline-regression.json
.venv/bin/alembic upgrade head
.venv/bin/alembic check
.venv/bin/python -m apps.api.publishing.bootstrap
.venv/bin/pytest -q --junitxml=artifacts/pytest.xml
npm run lint
npm run typecheck
node --check scripts/accept-claim-feedback.mjs
node --check scripts/accept-live-publishing-browser.mjs
node --check scripts/evaluate-public-papers-browser.mjs
node --check scripts/accept-vps-browser.mjs
node --check infrastructure/vps/collect-notices.mjs
docker compose build api web
# Test the exact built application, rather than a stale running image.
docker compose up -d api web --wait
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
