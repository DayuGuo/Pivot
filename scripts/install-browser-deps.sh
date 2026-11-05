#!/usr/bin/env bash
# CI host setup only. Keep the engines and failures visible; never skip a suite.
set -euo pipefail
cd "$(dirname "$0")/.."

cli_path="$(pwd -P)/node_modules/.bin/playwright"
node_path="$(command -v node || true)"
timeout_path=/usr/bin/timeout
if [[ ! -f "$cli_path" || "$node_path" != /* || ! -x "$node_path" || ! -x "$timeout_path" ]]; then
  echo "Browser dependency setup requires the installed Playwright CLI, absolute Node path and GNU timeout." >&2
  exit 2
fi

installer=("$timeout_path" --signal=TERM --kill-after=15s 300s "$node_path" "$cli_path" install-deps chromium firefox webkit)
if [[ "$(id -u)" != 0 ]]; then
  sudo_path="$(command -v sudo || true)"
  if [[ "$sudo_path" != /* || ! -x "$sudo_path" ]]; then
    echo "Browser dependency setup requires noninteractive sudo on this CI host." >&2
    exit 2
  fi
  # Elevate the timeout itself. A user-owned timeout cannot reliably terminate
  # root apt children started by the CLI's own sudo; their open pipe can leave
  # tee waiting beyond the deadline. Do not inherit secrets with sudo -E.
  installer=("$sudo_path" -n "${installer[@]}")
fi

mkdir -p artifacts/browser-deps
for attempt in 1 2; do
  echo "Installing Chromium, Firefox and WebKit host dependencies (attempt ${attempt}/2)."
  # The outer CI step also has a deadline. Kill an unresponsive installer after
  # TERM rather than allowing a repeated apt/network hang to consume the job.
  set +e
  "${installer[@]}" 2>&1 | tee "artifacts/browser-deps/attempt-${attempt}.log"
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
