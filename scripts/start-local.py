#!/usr/bin/env python3
"""Start local Compose while preserving an existing live model's scoped environment.

Only this project's selected API container is queried, through a captured exec
stream. No global authentication, inspect/config dump, key file or key argument.
An explicit EDITORIAL_MODEL_PROVIDER=mock remains an intentional switch to Mock.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
READ_MODEL = """import json,os
provider=os.environ.get('EDITORIAL_MODEL_PROVIDER','mock')
print(json.dumps({'provider':provider,'live':os.environ.get('EDITORIAL_MODEL_LIVE_ENABLED','false'),
'key':os.environ.get('DEEPSEEK_API_KEY','') if provider=='deepseek' else ''}))
"""


class LocalStartError(RuntimeError):
    """Fixed safe errors; never include a process object or captured environment."""


def preserved_environment():
    env = dict(os.environ)
    requested = env.get("EDITORIAL_MODEL_PROVIDER")
    if requested and requested not in {"mock", "deepseek"}:
        raise LocalStartError("模型提供商配置无效；未替换现有本地服务。")
    if env.get("EDITORIAL_MODEL_PROVIDER") == "mock":
        return env
    existing = subprocess.run(
        ["docker", "compose", "ps", "-a", "-q", "api"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if existing.returncode:
        raise LocalStartError("无法读取本地项目服务状态；未重建服务。")
    if not existing.stdout.strip():
        return env
    # Start the existing containers with their original environment before
    # reading it. --no-recreate never replaces a stopped live credential.
    warm = subprocess.run(
        ["docker", "compose", "up", "-d", "--no-recreate", "--wait", "db", "mailpit", "api"],
        cwd=ROOT,
        check=False,
    )
    if warm.returncode:
        raise LocalStartError("现有本地API未就绪；未用默认配置覆盖。请使用安全真实模型启动器恢复。")
    captured = subprocess.run(
        ["docker", "compose", "exec", "-T", "api", "python", "-c", READ_MODEL],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if captured.returncode:
        raise LocalStartError("无法安全恢复现有模型环境；未重建服务。")
    try:
        current = json.loads(captured.stdout)
        if not isinstance(current, dict) or set(current) != {"provider", "live", "key"}:
            raise ValueError
        if not all(isinstance(v, str) for v in current.values()):
            raise ValueError
    except (ValueError, TypeError):
        raise LocalStartError("现有模型环境格式无效；未重建服务。") from None
    if current["provider"] == "deepseek":
        key = env.get("DEEPSEEK_API_KEY") or current["key"]
        if not key or key != key.strip() or any(c.isspace() for c in key):
            raise LocalStartError("现有真实模型没有可恢复的环境凭据；未切换为Mock。")
        env["DEEPSEEK_API_KEY"] = key
        env["EDITORIAL_MODEL_PROVIDER"] = env.get("EDITORIAL_MODEL_PROVIDER") or "deepseek"
        env["EDITORIAL_MODEL_LIVE_ENABLED"] = (
            env.get("EDITORIAL_MODEL_LIVE_ENABLED") or current["live"]
        )
    elif current["provider"] != "mock":
        raise LocalStartError("现有模型提供商不受此启动器支持；未重建服务。")
    return env


def main():
    try:
        env = preserved_environment()
        result = subprocess.run(
            ["docker", "compose", "up", "-d", "--build", "--wait"],
            cwd=ROOT,
            env=env,
            check=False,
        )
    except LocalStartError as error:
        print(str(error), file=sys.stderr)
        return 2
    except OSError:
        print("无法执行本地Docker命令；请检查Docker与Compose。", file=sys.stderr)
        return 2
    if result.returncode:
        print("本地服务未全部就绪；未保存任何模型密钥文件。", file=sys.stderr)
        return result.returncode
    print("Publishing OS: http://localhost:3100/publishing")
    print("API: http://localhost:8100/docs\nMailpit: http://localhost:8025")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
