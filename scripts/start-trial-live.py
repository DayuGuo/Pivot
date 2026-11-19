#!/usr/bin/env python3
"""Start only the isolated local trial stack, then run bounded real-model acceptance."""

import argparse
import getpass
import os
import subprocess
import sys
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = [
    "docker",
    "--host",
    "unix:///var/run/docker.sock",
    "compose",
    "-p",
    "pivot-trial-live",
    "-f",
    "compose.yaml",
    "-f",
    "infrastructure/compose.trial-live.yaml",
]


def fresh_key():
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        if not sys.stdin.isatty():
            raise ValueError("fresh_environment_key_required")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("新的 DeepSeek 密钥（无回显，不保存）：")
    if (
        not key
        or any(c.isspace() for c in key)
        or key.lower().startswith(("mock", "test", "replace", "your"))
    ):
        raise ValueError("fresh_environment_key_required")
    return key


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", required=True)
    parser.parse_args()
    try:
        key = fresh_key()
        env = {**os.environ, "DEEPSEEK_API_KEY": key, "EMAIL_SEND_ENABLED": "false"}
        for name in ("DOCKER_HOST", "DOCKER_CONTEXT", "DOCKER_TLS_VERIFY", "DOCKER_CERT_PATH"):
            env.pop(name, None)
        # Fixed project/ports/volumes; never compose config, inspect, down -v or global auth.
        result = subprocess.run(
            COMPOSE + ["up", "--build", "-d", "--wait", "db", "api", "mailpit"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            timeout=600,
        )
        if result.returncode:
            print("独立试用服务启动失败；未输出配置或凭据，未改动主服务。", file=sys.stderr)
            return 1
        child_env = {**os.environ}
        child_env.pop("DEEPSEEK_API_KEY", None)
        return subprocess.run(
            [sys.executable, "evals/editorial_trial/live.py", "--live"],
            cwd=ROOT,
            env=child_env,
            timeout=900,
        ).returncode
    except (
        ValueError,
        getpass.GetPassWarning,
        OSError,
        EOFError,
        KeyboardInterrupt,
        subprocess.TimeoutExpired,
    ):
        print(
            "真实验收未完成：需要安全终端/有效环境密钥及可用本机 Docker；未保存密钥。",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
