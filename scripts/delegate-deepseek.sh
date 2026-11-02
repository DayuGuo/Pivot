#!/usr/bin/env bash
# Local interactive launcher. Never put a key in a command argument or this file.
set +x
set -euo pipefail
umask 077
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/python ]]; then
  printf 'Run ./scripts/setup.sh first.\n' >&2
  exit 1
fi
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  if [[ ! -t 0 ]]; then
    printf 'A fresh DEEPSEEK_API_KEY environment variable or an interactive terminal is required.\n' >&2
    exit 1
  fi
  read -r -s -p 'New DeepSeek API key (never one posted in chat; input hidden): ' DEEPSEEK_API_KEY
  printf '\n' >&2
  export DEEPSEEK_API_KEY
fi
trap 'unset DEEPSEEK_API_KEY' EXIT
.venv/bin/python -m packages.model_gateway.delegate \
  --kind react --task-file "${1:-specs/tasks/hermes-ui-review.md}" \
  --live --output-root artifacts/delegations
