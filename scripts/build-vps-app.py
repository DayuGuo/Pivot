#!/usr/bin/env python3
"""Build a self-contained private preview on a matching development/CI host, not VPS."""

import argparse
import gzip
import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def run(*args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["linux/amd64", "linux/arm64"])
    args = parser.parse_args()
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
    source = run("git", "rev-parse", "HEAD", capture_output=True, text=True).stdout.strip()
    if run("git", "status", "--porcelain", capture_output=True, text=True).stdout.strip():
        source += "-worktree"
    suffix = platform.replace("/", "-")
    tag = source[:12] + ("-worktree" if source.endswith("-worktree") else "") + "-" + suffix
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
    (destination / "bundle.json").write_text(
        json.dumps(
            {"source": source, "platform": platform, "images": images, "sha256": hashes}, indent=2
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
