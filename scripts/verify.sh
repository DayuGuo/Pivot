#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p artifacts
.venv/bin/python scripts/check-boundaries.py
.venv/bin/ruff check apps/api packages tests/api tests/mail_adapters evals infrastructure/migrations
.venv/bin/ruff format --check apps/api packages tests/api tests/mail_adapters evals infrastructure/migrations
.venv/bin/alembic upgrade head
.venv/bin/alembic check
.venv/bin/python -m apps.api.publishing.bootstrap
.venv/bin/pytest -q --junitxml=artifacts/pytest.xml
npm run lint
npm run typecheck
docker compose build web
npm run test:e2e
