"""Offline shell contract: bounded retries never convert an install failure to green."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def installer(tmp_path):
    (tmp_path / "scripts").mkdir()
    script = tmp_path / "scripts/install-browser-deps.sh"
    shutil.copyfile(ROOT / "scripts/install-browser-deps.sh", script)
    cli = tmp_path / "node_modules/.bin/playwright"
    cli.parent.mkdir(parents=True)
    cli.write_text(
        """#!/usr/bin/env bash
set -eu
counter="$TASK_FIXTURE_ROOT/cli-count"
count=0; [[ ! -f "$counter" ]] || read -r count < "$counter"
count=$((count + 1)); echo "$count" > "$counter"
read -ra statuses <<< "$TASK_FIXTURE_STATUSES"
echo "cli: $*"
echo "installer diagnostic $count" >&2
exit "${statuses[count - 1]:-0}"
"""
    )
    cli.chmod(0o755)
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    timeout = fake_bin / "timeout"
    timeout.write_text(
        """#!/usr/bin/env bash
set -eu
counter="$TASK_FIXTURE_ROOT/timeout-count"
count=0; [[ ! -f "$counter" ]] || read -r count < "$counter"
count=$((count + 1)); echo "$count" > "$counter"
echo "$*" >> "$TASK_FIXTURE_ROOT/timeout-arguments"
[[ "$1" == --signal=TERM && "$2" == --kill-after=15s && "$3" == 300s ]]
shift 3
if [[ "${TASK_FIXTURE_TIMEOUT:-}" == all || "${TASK_FIXTURE_TIMEOUT:-}" == "$count" ]]; then
  echo "simulated timeout $count" >&2
  exit 124
fi
exec "$@"
"""
    )
    timeout.chmod(0o755)
    sleep = fake_bin / "sleep"
    sleep.write_text(
        '#!/usr/bin/env bash\nset -eu\necho "$*" >> "$TASK_FIXTURE_ROOT/sleep-arguments"\n'
    )
    sleep.chmod(0o755)

    def run(statuses="0", timeout=""):
        # A minimal environment prevents unrelated developer/provider configuration
        # from entering this offline installer fixture.
        return subprocess.run(
            ["bash", str(script)],
            cwd=tmp_path,
            env={
                "PATH": str(fake_bin) + os.pathsep + os.defpath,
                "TASK_FIXTURE_ROOT": str(tmp_path),
                "TASK_FIXTURE_STATUSES": statuses,
                "TASK_FIXTURE_TIMEOUT": timeout,
            },
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

    return tmp_path, run


@pytest.mark.parametrize(
    "statuses,expected,attempts",
    [("0", 0, 1), ("17 0", 0, 2), ("17 23", 23, 2)],
)
def test_install_retry_keeps_all_engines_and_final_status(installer, statuses, expected, attempts):
    root, run = installer
    result = run(statuses)
    assert result.returncode == expected
    assert (root / "cli-count").read_text().strip() == str(attempts)
    logs = sorted((root / "artifacts/browser-deps").glob("attempt-*.log"))
    assert len(logs) == attempts
    for number, path in enumerate(logs, start=1):
        assert "cli: install-deps chromium firefox webkit" in path.read_text()
        assert f"installer diagnostic {number}" in path.read_text()
    if attempts == 2:
        assert (root / "sleep-arguments").read_text().strip() == "2"
        assert "failed with status 17" in result.stderr
    else:
        assert not (root / "sleep-arguments").exists()


@pytest.mark.parametrize("timeout,expected", [("1", 0), ("all", 124)])
def test_timeout_is_bounded_retried_and_never_hidden(installer, timeout, expected):
    root, run = installer
    result = run(timeout=timeout)
    assert result.returncode == expected
    assert (root / "timeout-count").read_text().strip() == "2"
    assert "simulated timeout 1" in (root / "artifacts/browser-deps/attempt-1.log").read_text()
    assert "failed with status 124" in result.stderr
    if expected == 124:
        assert not (root / "cli-count").exists()


def test_missing_local_cli_does_not_fetch_or_succeed(installer):
    root, run = installer
    (root / "node_modules/.bin/playwright").unlink()
    result = run()
    assert result.returncode == 2
    assert not (root / "timeout-count").exists()
    assert not (root / "artifacts/browser-deps").exists()
