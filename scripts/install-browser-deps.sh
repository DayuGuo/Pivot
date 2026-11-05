#!/usr/bin/env bash
# CI host setup only. Keep the engines and failures visible; never skip a suite.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -x node_modules/.bin/playwright ]] || ! command -v timeout >/dev/null; then
  echo "Browser dependency setup requires the installed Playwright CLI and GNU timeout." >&2
  exit 2
fi

mkdir -p artifacts/browser-deps
for attempt in 1 2; do
  echo "Installing Chromium, Firefox and WebKit host dependencies (attempt ${attempt}/2)."
  # The outer CI step also has a deadline. Kill an unresponsive installer after
  # TERM rather than allowing a repeated apt/network hang to consume the job.
  set +e
  timeout --signal=TERM --kill-after=15s 300s \
    ./node_modules/.bin/playwright install-deps chromium firefox webkit \
    2>&1 | tee "artifacts/browser-deps/attempt-${attempt}.log"
  statuses=("${PIPESTATUS[@]}")
  set -e
  if (( statuses[1] != 0 )); then
    echo "Could not retain the browser dependency installation log." >&2
    exit "${statuses[1]}"
  fi
  if (( statuses[0] == 0 )); then
    exit 0
  fi
  echo "Browser dependency attempt ${attempt} failed with status ${statuses[0]}." >&2
  if (( attempt == 2 )); then
    exit "${statuses[0]}"
  fi
  sleep 2
done
