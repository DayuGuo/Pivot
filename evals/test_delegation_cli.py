"""Exercise actual CLI boundaries without provider requests or confidential inputs."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def invoke(*args):
    env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
    return subprocess.run(
        [sys.executable, "-m", "packages.model_gateway.delegate", *map(str, args)],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=15,
    )


def test_public_task_file_generates_isolated_mock_and_sanitized_telemetry(tmp_path):
    task = tmp_path / "task.md"
    task.write_text("Public synthetic design review: do not copy this task into logs.")
    output_root = tmp_path / "results"
    result = invoke("--kind", "react", "--task-file", task, "--output-root", output_root)
    assert result.returncode == 0, result.stderr
    assert task.read_text() not in result.stdout
    data = json.loads(result.stdout)
    directory = Path(data["artifact_directory"])
    assert directory.parent == output_root
    assert data["telemetry"]["provider"] == "mock"
    assert json.loads((directory / "result.json").read_text())["requires_lead_review"] is True
    assert json.loads((directory / "telemetry.json").read_text())["cost_usd"] == 0
    assert directory.stat().st_mode & 0o077 == 0


def test_task_sources_are_mutually_exclusive(tmp_path):
    task = tmp_path / "task.md"
    task.write_text("Public synthetic task")
    result = invoke("--kind", "react", "--task", "public", "--task-file", task)
    assert result.returncode == 2
    assert "not allowed with argument" in result.stderr


@pytest.mark.parametrize("case", ["missing", "invalid_utf8", "oversized"])
def test_unreadable_task_files_fail_before_task_execution(tmp_path, case):
    task = tmp_path / "task.md"
    if case == "invalid_utf8":
        task.write_bytes(b"\xff")
    elif case == "oversized":
        task.write_text("x" * 12001)
    output_root = tmp_path / "results"
    result = invoke("--kind", "react", "--task-file", task, "--output-root", output_root)
    assert result.returncode == 2
    assert "task_file_" in result.stderr
    assert not output_root.exists()


def test_live_launcher_requires_safe_input_and_never_falls_back_to_mock():
    env = {k: v for k, v in os.environ.items() if k != "DEEPSEEK_API_KEY"}
    result = subprocess.run(
        ["bash", str(ROOT / "scripts/delegate-deepseek.sh")],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 1
    assert "fresh DEEPSEEK_API_KEY" in result.stderr
    assert not result.stdout
