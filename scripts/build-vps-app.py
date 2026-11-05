#!/usr/bin/env python3
"""Build a self-contained private preview on a matching development/CI host, not VPS."""

import argparse
import gzip
import hashlib
import json
import shutil
import stat
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Hash repository sources, not a developer's private state, credentials or build
# output. New files are admitted only in known source/documentation directories.
SOURCE_DIRECTORIES = {
    ".github",
    "apps",
    "docs",
    "evals",
    "infrastructure",
    "packages",
    "scripts",
    "specs",
    "tests",
}
ROOT_SOURCE_SUFFIXES = {
    ".css",
    ".html",
    ".ini",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".sh",
    ".svg",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}
EXCLUDED_DIRECTORIES = {
    ".git",
    ".venv",
    ".next",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "artifacts",
    "node_modules",
    "playwright-report",
    "test-results",
    "var",
    "privateenv",
    "private-env",
    "pivot-app-data",
}


def source_path_allowed(name, *, tracked):
    path = Path(name)
    if path.is_absolute() or ".." in path.parts:
        return False
    if any(
        part in EXCLUDED_DIRECTORIES
        or part.startswith((".env", "preview-state-", "preview-restore-"))
        for part in path.parts
    ):
        return False
    if path.name == "credentials.json" or path.suffix in {".pem", ".key", ".pyc", ".log"}:
        return False
    if path.name.endswith(".tsbuildinfo"):
        return False
    return (
        tracked
        or (len(path.parts) > 1 and path.parts[0] in SOURCE_DIRECTORIES)
        or (len(path.parts) == 1 and path.suffix.lower() in ROOT_SOURCE_SUFFIXES)
    )


def source_identity(*, allow_worktree=False):
    commit = run("git", "rev-parse", "HEAD", capture_output=True, text=True).stdout.strip()
    dirty = bool(
        run("git", "status", "--porcelain", "-z", capture_output=True).stdout.strip(b"\x00")
    )
    if dirty and not allow_worktree:
        raise SystemExit(
            "Candidate bundles require a clean source tree; use --allow-worktree only for local validation"
        )
    tracked = set(run("git", "ls-files", "-z", capture_output=True).stdout.split(b"\x00"))
    untracked = set(
        run(
            "git", "ls-files", "--others", "--exclude-standard", "-z", capture_output=True
        ).stdout.split(b"\x00")
    )
    digest = hashlib.sha256()
    for raw_name in sorted((tracked | untracked) - {b""}):
        name = raw_name.decode("utf-8", errors="surrogateescape")
        if not source_path_allowed(name, tracked=raw_name in tracked):
            continue
        path = ROOT / name
        try:
            info = path.lstat()
        except FileNotFoundError:
            # Deleted tracked files are absent from the actual tree.
            continue
        if not stat.S_ISREG(info.st_mode):
            raise SystemExit("Source inputs must be ordinary files; no symlink/submodule builds")
        digest.update(len(raw_name).to_bytes(8, "big"))
        digest.update(raw_name)
        digest.update(bytes([bool(info.st_mode & 0o111)]))
        with path.open("rb") as stream:
            digest.update(hashlib.file_digest(stream, "sha256").digest())
    tree = digest.hexdigest()
    return {
        "source": commit + ("-worktree-" + tree if dirty else ""),
        "commit": commit,
        "tree_sha256": tree,
        "worktree": dirty,
    }


def require_unchanged_source(identity):
    if source_identity(allow_worktree=True) != identity:
        raise SystemExit("Source changed during the build; no candidate bundle assembled")


def run(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["linux/amd64", "linux/arm64"])
    parser.add_argument(
        "--allow-worktree",
        action="store_true",
        help="Local validation only: bind actual source bytes",
    )
    args = parser.parse_args()
    identity = source_identity(allow_worktree=args.allow_worktree)
    native = run(
        "docker",
        "version",
        "--format",
        "{{.Server.Os}}/{{.Server.Arch}}",
        capture_output=True,
        text=True,
    ).stdout.strip()
    platform = args.platform or native
    if platform != native or platform not in {"linux/amd64", "linux/arm64"}:
        raise SystemExit(
            "Use a matching native builder (amd64 CI for RackNerd); no emulation claimed"
        )
    source = identity["source"]
    suffix = platform.replace("/", "-")
    tag = identity["commit"][:12]
    if identity["worktree"]:
        tag += "-worktree-" + identity["tree_sha256"][:16]
    tag += "-" + suffix
    images = {part: f"pivot-app-{part}:{tag}" for part in ("api", "web", "db")}
    for part in ("api", "web"):
        run(
            "docker",
            "build",
            "--platform",
            platform,
            "-f",
            f"infrastructure/vps/{part}.Dockerfile",
            "-t",
            images[part],
            ".",
        )
    run("docker", "pull", "--platform", platform, "postgres:17-alpine")
    run("docker", "tag", "postgres:17-alpine", images["db"])
    require_unchanged_source(identity)
    image_ids = {
        part: run(
            "docker",
            "image",
            "inspect",
            name,
            "--format",
            "{{.Id}}",
            capture_output=True,
            text=True,
        ).stdout.strip()
        for part, name in images.items()
    }
    destination = ROOT / "artifacts" / f"pivot-app-{suffix}"
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("manage.py", "compose.yaml", "README.md", "NOTICES.md"):
        shutil.copyfile(ROOT / "infrastructure/vps" / name, destination / name)
    for ext in ("pdf", "docx"):
        shutil.copyfile(
            ROOT / "tests/documents" / f"synthetic-manuscript.{ext}",
            destination / f"synthetic-manuscript.{ext}",
        )
    archive = destination / "images.tar.gz"
    with (
        archive.open("wb") as raw,
        gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, compresslevel=3) as compressed,
    ):
        process = subprocess.Popen(
            ["docker", "save", *images.values()], cwd=ROOT, stdout=subprocess.PIPE
        )
        try:
            shutil.copyfileobj(process.stdout, compressed)
        finally:
            process.stdout.close()
        if process.wait() != 0:
            raise SystemExit("Image export failed")
    hashes = {}
    included = [
        "manage.py",
        "compose.yaml",
        "README.md",
        "NOTICES.md",
        "synthetic-manuscript.pdf",
        "synthetic-manuscript.docx",
        "images.tar.gz",
    ]
    for name in included:
        with (destination / name).open("rb") as stream:
            hashes[name] = hashlib.file_digest(stream, "sha256").hexdigest()
    require_unchanged_source(identity)
    (destination / "bundle.json").write_text(
        json.dumps(
            {
                "source": source,
                "source_commit": identity["commit"],
                "source_tree_sha256": identity["tree_sha256"],
                "worktree": identity["worktree"],
                "platform": platform,
                "images": images,
                "image_ids": image_ids,
                "sha256": hashes,
            },
            indent=2,
        )
        + "\n"
    )
    with tarfile.open(
        ROOT / "artifacts" / f"pivot-app-{suffix}.tar.gz", "w:gz", compresslevel=1
    ) as output:
        for name in included + ["bundle.json"]:
            output.add(destination / name, arcname=destination.name + "/" + name, recursive=False)
    package = ROOT / "artifacts" / f"pivot-app-{suffix}.tar.gz"
    with package.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    (ROOT / "artifacts" / f"pivot-app-{suffix}-SHA256SUMS").write_text(
        f"{digest}  {package.name}\n"
    )
    print(
        f"Private-preview bundle: {package}; {package.stat().st_size} bytes; no credentials/data included"
    )


if __name__ == "__main__":
    main()
