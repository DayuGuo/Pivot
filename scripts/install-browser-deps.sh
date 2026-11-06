#!/usr/bin/env bash
# CI host setup only. Keep the engines and failures visible; never skip a suite.
set -euo pipefail
cd "$(dirname "$0")/.."

engines=("$@")
if (( $# == 0 )); then engines=(chromium firefox webkit); fi
declare -A seen_engines=()
for engine in "${engines[@]}"; do
  case "$engine" in chromium|firefox|webkit) ;; *) echo "Unsupported browser dependency engine." >&2; exit 2 ;; esac
  if [[ "${seen_engines[$engine]:-}" == yes ]]; then
    echo "Duplicate browser dependency engine." >&2; exit 2
  fi
  seen_engines[$engine]=yes
done

cli_path="$(pwd -P)/node_modules/.bin/playwright"
node_path="$(command -v node || true)"
timeout_path=/usr/bin/timeout
if [[ ! -f "$cli_path" || "$node_path" != /* || ! -x "$node_path" || ! -x "$timeout_path" ]]; then
  echo "Browser dependency setup requires the installed Playwright CLI, absolute Node path and GNU timeout." >&2
  exit 2
fi

installer=("$timeout_path" --signal=TERM --kill-after=15s 300s "$node_path" "$cli_path" install-deps "${engines[@]}")
fallback=(/usr/bin/python3 "$(pwd -P)/scripts/ci-ubuntu-apt-fallback.py")
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
  fallback=("$sudo_path" -n --preserve-env=GITHUB_ACTIONS,RUNNER_OS,RUNNER_ARCH,RUNNER_TEMP,RUNNER_ENVIRONMENT "${fallback[@]}")
fi

mkdir -p artifacts/browser-deps
for attempt in 1 2; do
  echo "Installing browser host dependencies (${engines[*]}; attempt ${attempt}/2)."
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
  if [[ "${GITHUB_ACTIONS:-}" == true ]]; then
    if "${fallback[@]}"; then
      echo "The second browser dependency attempt will use the official HTTPS CI mirror configuration."
    else
      echo "Official CI mirror fallback was not confirmed; retrying dependency installation." >&2
    fi
  fi
  sleep 2
done
