#!/usr/bin/env python3
"""Offline private-preview lifecycle. No shell, secret arguments, or config dumps."""

import argparse
import fcntl
import getpass
import hashlib
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent


class PreviewError(Exception):
    pass


def require(ok, message):
    if not ok:
        raise PreviewError(message)


def checked_run(args, **kwargs):
    result = subprocess.run(args, check=False, **kwargs)
    require(
        result.returncode == 0,
        "Command failed; services/data retained. Inspect the named service, not its environment.",
    )
    return result


def secure_state(state):
    require(not state.is_symlink() and state.is_dir(), "State directory missing or a symlink")
    info = state.stat()
    require(
        info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
        "State directory must be owned by you, mode700",
    )


def read_config(state):
    secure_state(state)
    path = state / "credentials.json"
    require(path.is_file() and not path.is_symlink(), "State credentials missing")
    info = path.stat()
    require(
        info.st_uid == os.getuid() and info.st_mode & 0o077 == 0,
        "Credentials must be owned by you, mode600",
    )
    config = json.loads(path.read_text())
    validate_config(config)
    return config


def validate_config(config):
    require(
        set(config) == {"project", "port", "email", "password", "db_password", "key", "access"},
        "Unknown state configuration",
    )
    require(
        isinstance(config["project"], str)
        and re.fullmatch(r"pivot-[a-z0-9-]{1,35}", config["project"]),
        "Use a dedicated pivot-* project name",
    )
    require(
        type(config["port"]) is int and 1024 <= config["port"] <= 65535, "Invalid loopback port"
    )
    require(
        isinstance(config["email"], str)
        and re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", config["email"])
        and len(config["email"]) <= 254
        and not config["email"].endswith("@publishing.test"),
        "Use your own operator email",
    )
    require(
        isinstance(config["password"], str) and 16 <= len(config["password"]) <= 256,
        "Operator password must have16–256 characters",
    )
    require(
        isinstance(config["db_password"], str)
        and re.fullmatch(r"[A-Za-z0-9_-]{40,100}", config["db_password"]),
        "Invalid private DB credential",
    )
    require(config["access"] in {"tunnel", "https"}, "Access must be tunnel or https")
    key = config["key"]
    require(
        isinstance(key, str)
        and (not key or (len(key) >= 24 and not any(c.isspace() for c in key))),
        "Invalid model credential shape",
    )


def configure(state, *, email, password, key, access, port, project):
    config = dict(
        project=project,
        port=port,
        email=email.strip().lower(),
        password=password,
        key=key,
        access=access,
        db_password=secrets.token_urlsafe(36),
    )
    validate_config(config)
    require(
        not state.exists() and not state.is_symlink(),
        "State already exists; use the existing state, never reinitialise it",
    )
    state.mkdir(parents=True, mode=0o700)
    path = state / "credentials.json"
    with os.fdopen(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600), "w") as stream:
        json.dump(config, stream)
    return config


def release():
    manifest = json.loads((BUNDLE / "bundle.json").read_text())
    require(manifest.get("platform") in {"linux/amd64", "linux/arm64"}, "Unknown bundle platform")
    for name, digest in manifest["sha256"].items():
        require(Path(name).name == name, "Invalid bundle filename")
        with (BUNDLE / name).open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        require(actual == digest, "Bundle checksum mismatch; no images loaded")
    return manifest


def environment(config, manifest):
    # Do not inherit unrelated project/model settings or a caller's .env file.
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        in {
            "PATH",
            "HOME",
            "LANG",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_TLS_VERIFY",
            "DOCKER_CERT_PATH",
            "XDG_RUNTIME_DIR",
        }
    }
    env.update(
        PIVOT_API_IMAGE=manifest["images"]["api"],
        PIVOT_WEB_IMAGE=manifest["images"]["web"],
        PIVOT_DB_IMAGE=manifest["images"]["db"],
        PIVOT_DB_PASSWORD=config["db_password"],
        PIVOT_OPERATOR_EMAIL=config["email"],
        PIVOT_OPERATOR_PASSWORD=config["password"],
        PIVOT_MODEL_PROVIDER="deepseek" if config["key"] else "mock",
        PIVOT_MODEL_LIVE="true" if config["key"] else "false",
        PIVOT_MODEL_KEY=config["key"],
        PIVOT_COOKIE_SECURE="true" if config["access"] == "https" else "false",
        PIVOT_PORT=str(config["port"]),
    )
    return env


class Deployment:
    def __init__(self, state, config, manifest):
        self.state, self.config, self.manifest = state, config, manifest
        self.env = environment(config, manifest)
        self.command = [
            "docker",
            "compose",
            "--project-name",
            config["project"],
            "--env-file",
            "/dev/null",
            "-f",
            str(BUNDLE / "compose.yaml"),
        ]

    def dc(self, *args, **kwargs):
        return checked_run(self.command + list(args), env=self.env, cwd=BUNDLE, **kwargs)

    def raw(self, *args, **kwargs):
        return checked_run(["docker", *args], env=self.env, **kwargs)

    def existing(self):
        return bool(self.dc("ps", "-a", "-q", stdout=subprocess.PIPE, text=True).stdout.strip())

    def load(self):
        platform = self.raw(
            "version",
            "--format",
            "{{.Server.Os}}/{{.Server.Arch}}",
            stdout=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        require(platform == self.manifest["platform"], "Docker platform mismatch; no images loaded")
        self.raw("load", "-i", str(BUNDLE / "images.tar.gz"), stdout=subprocess.DEVNULL)

    def up(self, *, updating=False, restoring=False):
        installed = self.state / "installed.json"
        if not installed.exists() and not restoring:
            marker = self.state / "managed.json"
            if marker.exists():
                require(
                    json.loads(marker.read_text())
                    == {"project": self.config["project"], "source": self.manifest["source"]},
                    "Retry a failed first start with its original state and bundle",
                )
            else:
                require(
                    not self.existing(), "Existing containers require their original private state"
                )
                self.require_fresh_volumes()
                marker.write_text(
                    json.dumps(
                        {"project": self.config["project"], "source": self.manifest["source"]}
                    )
                )
        if (
            installed.exists()
            and json.loads(installed.read_text())["source"] != self.manifest["source"]
        ):
            require(
                updating,
                "New version requires update (automatic backup); ordinary up left data unchanged",
            )
        self.load()
        self.dc("up", "-d", "--no-build", "--pull", "never", "--wait", "--wait-timeout", "240")
        self.health()
        installed.write_text(json.dumps({"source": self.manifest["source"]}) + "\n")

    def health(self):
        url = f"http://127.0.0.1:{self.config['port']}/api/health"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(url, timeout=10) as response:
                data = json.load(response)
        except (urllib.error.URLError, ValueError):
            raise PreviewError("Private preview health check failed") from None
        require(data.get("email_send_enabled") is False, "Mail must remain disabled")
        expected = "deepseek" if self.config["key"] else "mock"
        require(
            data.get("editorial_model", {}).get("provider") == expected,
            "Unexpected model configuration",
        )
        print(
            json.dumps(
                {
                    "healthy": True,
                    "provider": expected,
                    "email_send_enabled": False,
                    "loopback_port": self.config["port"],
                }
            )
        )

    def backup(self):
        require(self.existing(), "No installed application to back up")
        destination = (
            self.state
            / "backups"
            / (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(4))
        )
        destination.mkdir(parents=True, mode=0o700)
        # A stopped application cannot write DB or CAS while both are captured.
        running = self.dc(
            "ps", "--status", "running", "--services", stdout=subprocess.PIPE, text=True
        ).stdout.split()
        self.dc("stop", "web", "api")
        try:
            with (destination / "database.dump").open("xb") as stream:
                self.dc(
                    "exec",
                    "-T",
                    "db",
                    "pg_dump",
                    "-U",
                    "publishing",
                    "-d",
                    "publishing",
                    "-Fc",
                    stdout=stream,
                )
            require((destination / "database.dump").stat().st_size > 0, "Empty database backup")
            with (destination / "database.dump").open("rb") as stream:
                self.dc(
                    "exec",
                    "-T",
                    "db",
                    "pg_restore",
                    "--list",
                    stdin=stream,
                    stdout=subprocess.DEVNULL,
                )
            self.dc("cp", "api:/data/publishing-files/.", str(destination / "files"))
            hashes = {}
            for path in sorted(destination.rglob("*")):
                require(not path.is_symlink(), "Backup must not contain symlinks")
                if path.is_file():
                    with path.open("rb") as stream:
                        hashes[str(path.relative_to(destination))] = hashlib.file_digest(
                            stream, "sha256"
                        ).hexdigest()
            (destination / "backup.json").write_text(
                json.dumps(
                    {
                        "source": json.loads((self.state / "installed.json").read_text())["source"],
                        "sha256": hashes,
                    },
                    indent=2,
                )
            )
        finally:
            # Start existing containers without recreating them or substituting new images.
            if "api" in running:
                self.dc("start", "api")
            if "web" in running:
                self.dc("start", "web")
        print("Private backup: " + str(destination))
        return destination

    def require_fresh_volumes(self):
        for volume in ("db", "files"):
            result = subprocess.run(
                ["docker", "volume", "inspect", self.config["project"] + "_" + volume],
                env=self.env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            require(
                result.returncode != 0,
                "Restore refuses an existing data volume; use a fresh project",
            )

    def restore(self, source):
        require(not self.existing(), "Restore requires a fresh independent project")
        self.require_fresh_volumes()
        secure_state(source)
        require(all(not p.is_symlink() for p in source.rglob("*")), "Backup symlinks are forbidden")
        metadata = json.loads((source / "backup.json").read_text())
        for name, digest in metadata["sha256"].items():
            target = source / name
            require(
                not Path(name).is_absolute()
                and ".." not in Path(name).parts
                and not target.is_symlink(),
                "Invalid backup path",
            )
            with target.open("rb") as stream:
                require(
                    hashlib.file_digest(stream, "sha256").hexdigest() == digest,
                    "Backup checksum mismatch",
                )
        require(
            {str(p.relative_to(source)) for p in source.rglob("*") if p.is_file()}
            == set(metadata["sha256"]) | {"backup.json"},
            "Backup contains unverified files",
        )
        require(
            metadata["source"] == self.manifest["source"],
            "Restore with the original backup's bundle first",
        )
        (self.state / "managed.json").write_text(
            json.dumps({"project": self.config["project"], "source": self.manifest["source"]})
        )
        self.load()
        self.dc("up", "-d", "--wait", "db")
        with (source / "database.dump").open("rb") as stream:
            self.dc(
                "exec",
                "-T",
                "db",
                "pg_restore",
                "-U",
                "publishing",
                "-d",
                "publishing",
                "--no-owner",
                "--exit-on-error",
                stdin=stream,
            )
        self.dc("create", "--no-recreate", "api")
        self.dc("cp", str(source / "files") + "/.", "api:/data/publishing-files/")
        self.up(restoring=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["init", "up", "status", "stop", "backup", "restore", "update"]
    )
    parser.add_argument("--state", required=True, type=Path)
    parser.add_argument("--project", default="pivot-app")
    parser.add_argument("--port", type=int, default=3210)
    parser.add_argument("--access", choices=["tunnel", "https"], default="tunnel")
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    state = args.state.expanduser().absolute()
    try:
        manifest = release()
        if args.command == "init":
            email = input("Operator email (login only, never sends mail): ")
            password = getpass.getpass("Private login password (16+ characters, no echo): ")
            require(password == getpass.getpass("Confirm login password: "), "Passwords differ")
            key = (
                ""
                if args.mock
                else os.getenv("DEEPSEEK_API_KEY", "")
                or getpass.getpass("Fresh DeepSeek key (blank = explicit Mock, no echo): ")
            )
            configure(
                state,
                email=email,
                password=password,
                key=key,
                access=args.access,
                port=args.port,
                project=args.project,
            )
            print("Private state created; credentials not printed. Run up with the same --state.")
            return
        config = read_config(state)
        with (state / "operation.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            deployment = Deployment(state, config, manifest)
            if args.command == "up":
                deployment.up()
            elif args.command == "status":
                deployment.dc("ps")
                deployment.health()
            elif args.command == "stop":
                deployment.dc("stop")
            elif args.command == "backup":
                deployment.backup()
            elif args.command == "restore":
                require(args.backup is not None, "restore requires --backup")
                deployment.restore(args.backup.absolute())
            elif args.command == "update":
                require(deployment.existing(), "Update requires the existing project's state")
                deployment.backup()
                deployment.up(updating=True)
    except (PreviewError, OSError, ValueError, KeyError) as error:
        # Never print exception text: it could include malformed secret input.
        if isinstance(error, PreviewError):
            print(str(error), file=sys.stderr)
        else:
            print(
                "Private preview operation failed safely; check permissions/state and retain data.",
                file=sys.stderr,
            )
        raise SystemExit(2) from None


if __name__ == "__main__":
    main()
