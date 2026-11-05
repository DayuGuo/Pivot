#!/usr/bin/env python3
"""Official HTTPS mirrors on an ephemeral GitHub-hosted Ubuntu 24.04 CI runner only."""

import json
import os
import platform
import re
import stat
import sys
import tempfile
from pathlib import Path

INITIAL_MIRRORS = [
    ("http://azure.archive.ubuntu.com/ubuntu/", 1),
    ("https://archive.ubuntu.com/ubuntu/", 2),
    ("https://security.ubuntu.com/ubuntu/", 3),
]
HTTPS_MIRRORS = [
    ("https://archive.ubuntu.com/ubuntu/", 1),
    ("https://security.ubuntu.com/ubuntu/", 2),
]
MIRROR_TEXT = "".join(f"{url}\tpriority:{priority}\n" for url, priority in HTTPS_MIRRORS).encode()
NETWORK_TEXT = (
    b'Acquire::http::Timeout "30";\nAcquire::https::Timeout "30";\nAcquire::Retries "1";\n'
)
MIRROR_PATH = "etc/apt/apt-mirrors.txt"
NETWORK_PATH = "etc/apt/apt.conf.d/zzz-pivot-ci-network"
SAFE_CONTEXT = {
    "GITHUB_ACTIONS": "true",
    "RUNNER_OS": "Linux",
    "RUNNER_ARCH": "X64",
    "RUNNER_ENVIRONMENT": "github-hosted",
}


class FallbackError(Exception):
    pass


def require(condition):
    if not condition:
        # No file content, environment value, proxy or URL enters diagnostics.
        raise FallbackError(
            "Official CI mirror fallback refused an unexpected host or configuration."
        )


def ordinary_directory(path):
    # Check the full chain without resolving/following a symlink.
    for directory in [*reversed(path.parents), path]:
        require(stat.S_ISDIR(directory.lstat().st_mode))


def read_regular(path):
    ordinary_directory(path.parent)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not info.st_mode & 0o022 and info.st_size <= 16384)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        current = os.fstat(stream.fileno())
        require(current.st_ino == info.st_ino and current.st_dev == info.st_dev)
        return stream.read()


def checked_mirrors(raw):
    lines = raw.decode("utf-8").splitlines()
    records = []
    for line in lines:
        if not line.strip():
            continue
        match = re.fullmatch(r"(https?://\S+)\s+priority:([1-3])", line.strip())
        require(match is not None)
        records.append((match[1], int(match[2])))
    # Exact approved endpoints/priority tuples reject credentials, query strings,
    # third-party mirrors and changes to authentication/trust configuration.
    require(records == INITIAL_MIRRORS or records == HTTPS_MIRRORS)


def write_atomic(path, raw):
    ordinary_directory(path.parent)
    if path.exists() or path.is_symlink():
        read_regular(path)
    descriptor, temporary = tempfile.mkstemp(prefix=".pivot-ci-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), 0o644)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def apply_fallback(*, root=Path("/"), environ=None, uid=None, system=None, machine=None):
    # root and host inputs are injectable for offline tests only; the CLI accepts
    # no paths or host overrides. No real /etc changes occur in those tests.
    environ = os.environ if environ is None else environ
    require(all(environ.get(key) == value for key, value in SAFE_CONTEXT.items()))
    require((os.geteuid() if uid is None else uid) == 0)
    require((platform.system() if system is None else system) == "Linux")
    require((platform.machine() if machine is None else machine) in {"x86_64", "amd64"})
    require(environ.get("RUNNER_TEMP") == "/home/runner/work/_temp")
    release = {}
    # Ubuntu's /etc/os-release is normally a symlink. Read its fixed canonical
    # distribution file instead; source and backup paths remain no-follow.
    for line in read_regular(root / "usr/lib/os-release").decode().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            release[key] = value.strip().strip('"')
    require(release.get("ID") == "ubuntu" and release.get("VERSION_ID") == "24.04")
    mirror, network = root / MIRROR_PATH, root / NETWORK_PATH
    original = read_regular(mirror)
    checked_mirrors(original)
    ordinary_directory(network.parent)
    old_network = read_regular(network) if network.exists() or network.is_symlink() else None
    require(old_network is None or old_network == NETWORK_TEXT)
    temporary_root = root / environ["RUNNER_TEMP"].lstrip("/")
    ordinary_directory(temporary_root)
    backup = Path(tempfile.mkdtemp(prefix="pivot-apt-backup-", dir=temporary_root))
    snapshots = [(mirror, original, MIRROR_TEXT), (network, old_network, NETWORK_TEXT)]
    for index, (_, raw, _) in enumerate(snapshots):
        if raw is not None:
            with os.fdopen(
                os.open(
                    backup / f"original-{index}.bin", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
                ),
                "wb",
            ) as stream:
                stream.write(raw)
    with os.fdopen(
        os.open(backup / "manifest.json", os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w"
    ) as stream:
        json.dump(
            {"paths": [MIRROR_PATH, NETWORK_PATH], "present": [True, old_network is not None]},
            stream,
        )
    changed = []
    try:
        for path, old, new in snapshots:
            require((read_regular(path) if path.exists() or path.is_symlink() else None) == old)
            if old != new:
                write_atomic(path, new)
                changed.append((path, old))
    except (OSError, FallbackError):
        for path, old in reversed(changed):
            if old is None:
                path.unlink(missing_ok=True)
            else:
                write_atomic(path, old)
        raise
    return len(changed)


def main():
    try:
        require(len(sys.argv) == 1)
        changed = apply_fallback()
        print(f"Official Ubuntu HTTPS CI mirrors ready; updated files: {changed}.")
        print(
            "Configured: Acquire::http::Timeout=30; Acquire::https::Timeout=30; Acquire::Retries=1"
        )
    except (FallbackError, OSError, ValueError):
        print("Official CI mirror fallback refused or failed.", file=sys.stderr)
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
