#!/usr/bin/env python3
"""Start local workbench with an explicitly supplied fresh environment credential.

No key in arguments, files, output or Codex configuration. Ctrl-C cancels safely.
"""

import getpass
import os
import subprocess
import sys
from pathlib import Path


def main():
    root = Path(__file__).resolve().parent.parent
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not key:
        if not sys.stdin.isatty():
            print(
                "缺少新的 DEEPSEEK_API_KEY。请在交互终端运行本脚本，无回显输入新密钥。",
                file=sys.stderr,
            )
            return 2
        key = getpass.getpass("新的 DeepSeek API Key（无回显，不保存）：")
    if (
        not key
        or key != key.strip()
        or any(c.isspace() for c in key)
        or key.lower().startswith(("test", "mock", "replace", "your"))
    ):
        print("密钥未配置；未启动真实模型。", file=sys.stderr)
        return 2
    env = {
        **os.environ,
        "DEEPSEEK_API_KEY": key,
        "EDITORIAL_MODEL_PROVIDER": "deepseek",
        "EDITORIAL_MODEL_LIVE_ENABLED": "true",
    }
    # Do not run compose config/inspect or print process environment.
    result = subprocess.run(
        ["docker", "compose", "up", "--build", "-d", "--wait"], cwd=root, env=env, check=False
    )
    if result.returncode:
        print("本地服务启动未完成，请检查服务状态；密钥未写入项目文件。", file=sys.stderr)
        return result.returncode
    print("本地真实模型工作台已启动：http://localhost:3100/workbench")
    print(
        "请运行 .venv/bin/python scripts/smoke-live-model.py 验证实际工具调用。邮件发送保持关闭。"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, EOFError):
        print("\n已取消，未保存密钥。", file=sys.stderr)
        raise SystemExit(130) from None
