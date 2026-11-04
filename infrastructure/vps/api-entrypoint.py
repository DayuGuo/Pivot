"""Private-preview image only; deterministic fail-closed startup, no secret output."""

import os
import subprocess


def main():
    if (
        os.environ.get("EMAIL_SEND_ENABLED") != "false"
        or os.environ.get("PIVOT_BOOTSTRAP_PROFILE") != "private-preview"
    ):
        raise SystemExit("Private preview requires mail disabled and private bootstrap")
    root = "/data/publishing-files"
    os.makedirs(root, exist_ok=True)
    # Dedicated application volume only. Restored files must belong to the service
    # user; never follow symlinks into another filesystem.
    for base, dirs, files in os.walk(root, followlinks=False):
        os.chown(base, 10001, 10001, follow_symlinks=False)
        for name in dirs + files:
            os.chown(os.path.join(base, name), 10001, 10001, follow_symlinks=False)
    os.setgroups([])
    os.setgid(10001)
    os.setuid(10001)
    subprocess.run(["alembic", "upgrade", "head"], check=True)
    subprocess.run(["python", "-m", "apps.api.publishing.bootstrap"], check=True)
    os.execvp(
        "uvicorn",
        [
            "uvicorn",
            "apps.api.publishing.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8100",
            "--workers",
            "1",
            "--limit-concurrency",
            "8",
            "--no-access-log",
        ],
    )


if __name__ == "__main__":
    main()
