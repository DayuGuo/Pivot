"""Source provenance and real Uvicorn protocol contracts, without Docker or sockets."""

import asyncio
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest
from uvicorn import Config
from uvicorn.protocols.http.h11_impl import H11Protocol
from uvicorn.server import ServerState

from apps.api.publishing.work_limits import RequestAdmission

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("candidate_builder", ROOT / "scripts/build-vps-app.py")
entrypoint = load("candidate_entrypoint", ROOT / "infrastructure/vps/api-entrypoint.py")


@pytest.fixture
def source_tree(tmp_path, monkeypatch):
    env = {"PATH": os.defpath, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, env=env, check=True, capture_output=True, text=True
        ).stdout.strip()

    git("init", "-q")
    (tmp_path / "apps/api").mkdir(parents=True)
    (tmp_path / "apps/api/example.py").write_text("value = 1\n")
    (tmp_path / ".gitignore").write_text("artifacts/\n.env*\n")
    git("add", ".")
    git(
        "-c",
        "user.name=Candidate fixture",
        "-c",
        "user.email=candidate@example.test",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "Synthetic isolated source fixture",
    )
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    return tmp_path, git


def test_clean_candidate_preserves_commit_identity(source_tree):
    _, git = source_tree
    identity = builder.source_identity()
    assert identity["source"] == git("rev-parse", "HEAD")
    assert not identity["worktree"]
    assert len(identity["tree_sha256"]) == 64


def test_dirty_build_requires_explicit_local_flag_and_distinguishes_actual_bytes(source_tree):
    root, _ = source_tree
    path = root / "apps/api/example.py"
    path.write_text("value = 2\n")
    with pytest.raises(SystemExit, match="clean source tree"):
        builder.source_identity()
    first = builder.source_identity(allow_worktree=True)
    path.write_text("value = 3\n")
    second = builder.source_identity(allow_worktree=True)
    assert first["commit"] == second["commit"]
    assert first["source"] != second["source"]
    assert first["source"].endswith(first["tree_sha256"])


def test_new_source_deletion_and_executable_mode_are_part_of_identity(source_tree):
    root, _ = source_tree
    baseline = builder.source_identity()
    new_source = root / "apps/api/new.py"
    new_source.write_text("value = 4\n")
    added = builder.source_identity(allow_worktree=True)
    assert added["tree_sha256"] != baseline["tree_sha256"]
    new_source.chmod(0o755)
    executable = builder.source_identity(allow_worktree=True)
    assert executable["tree_sha256"] != added["tree_sha256"]
    (root / "apps/api/example.py").unlink()
    deleted = builder.source_identity(allow_worktree=True)
    assert deleted["tree_sha256"] != executable["tree_sha256"]


def test_untracked_root_source_changes_cannot_share_a_worktree_identity(source_tree):
    root, _ = source_tree
    path = root / "NEW.md"
    path.write_text("First local candidate documentation.\n")
    first = builder.source_identity(allow_worktree=True)
    path.write_text("Second local candidate documentation.\n")
    second = builder.source_identity(allow_worktree=True)
    assert first["commit"] == second["commit"]
    assert first["source"] != second["source"]


def test_provenance_never_reads_private_state_or_build_output(source_tree, monkeypatch):
    root, _ = source_tree
    baseline = builder.source_identity()
    private_paths = [
        root / "artifacts/report.json",
        root / ".env.local",
        root / "apps/api/privateenv/config.json",
        root / "apps/web/credentials.json",
        root / "infrastructure/private-env/config.txt",
        root / "apps/api/nested/.env.production",
    ]
    for path in private_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic fixture excluded from build provenance\n")
    ordinary_open = Path.open

    def guarded_open(path, *args, **kwargs):
        assert path not in private_paths, "Provenance attempted to inspect excluded private data"
        return ordinary_open(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", guarded_open)
    after = builder.source_identity(allow_worktree=True)
    assert after["tree_sha256"] == baseline["tree_sha256"]


def test_symlink_source_is_rejected_without_reading_its_target(source_tree):
    root, _ = source_tree
    target = root / "outside-source.txt"
    target.write_text("synthetic untrusted target\n")
    (root / "apps/api/linked.py").symlink_to(target)
    with pytest.raises(SystemExit, match="ordinary files"):
        builder.source_identity(allow_worktree=True)


def test_build_freeze_detects_a_mid_build_source_change(source_tree):
    root, _ = source_tree
    identity = builder.source_identity()
    builder.require_unchanged_source(identity)
    (root / "apps/api/example.py").write_text("value = 5\n")
    with pytest.raises(SystemExit, match="Source changed"):
        builder.require_unchanged_source(identity)


class MemoryTransport(asyncio.Transport):
    def __init__(self):
        self.output = bytearray()
        self.closed = False

    def get_extra_info(self, name, default=None):
        return {"peername": ("127.0.0.1", 12345), "sockname": ("127.0.0.1", 8100)}.get(
            name, default
        )

    def write(self, data):
        self.output.extend(data)

    def close(self):
        self.closed = True

    def is_closing(self):
        return self.closed

    def pause_reading(self):
        pass

    def resume_reading(self):
        pass


def configured_limit():
    command = entrypoint.SERVER_COMMAND
    assert command[command.index("--workers") + 1] == "1"
    assert command[command.index("--timeout-keep-alive") + 1] == "2"
    assert command[command.index("--backlog") + 1] == "64"
    return int(command[command.index("--limit-concurrency") + 1])


def open_protocols(app, connections, *, limit):
    config = Config(
        app, http="h11", ws="none", lifespan="off", limit_concurrency=limit, log_config=None
    )
    state = ServerState()
    protocols = [H11Protocol(config, state, {}) for _ in range(connections)]
    transports = [MemoryTransport() for _ in protocols]
    for protocol, transport in zip(protocols, transports, strict=True):
        protocol.connection_made(transport)
    return state, protocols, transports


REQUEST = b"GET /api/fixture HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"


@pytest.mark.parametrize("connections,expected", [(8, 200), (31, 200), (32, 503)])
def test_private_server_allows_app_admission_but_keeps_transport_cap(connections, expected):
    async def scenario():
        called = []

        async def app(scope, receive, send):
            called.append(scope["path"])
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})

        state, protocols, transports = open_protocols(app, connections, limit=configured_limit())
        protocols[0].data_received(REQUEST)
        await asyncio.gather(*list(state.tasks))
        assert f"HTTP/1.1 {expected} ".encode() in transports[0].output
        assert bool(called) == (expected == 200)
        for protocol in protocols:
            protocol.connection_lost(None)

    asyncio.run(scenario())


def test_private_server_preserves_application_429_and_eight_active_requests():
    async def scenario():
        release = asyncio.Event()
        entered = 0
        active = 0
        peak = 0

        async def app(scope, receive, send):
            nonlocal entered, active, peak
            entered += 1
            active += 1
            peak = max(peak, active)
            await release.wait()
            await send({"type": "http.response.start", "status": 200, "headers": []})
            await send({"type": "http.response.body", "body": b"ok"})
            active -= 1

        admitted = RequestAdmission(app)
        state, protocols, transports = open_protocols(admitted, 25, limit=configured_limit())
        for protocol in protocols:
            protocol.data_received(REQUEST)
        try:
            for _ in range(100):
                await asyncio.sleep(0)
                if entered == 8 and any(b"HTTP/1.1 429 " in t.output for t in transports):
                    break
            assert entered == 8
            assert sum(b"HTTP/1.1 429 " in t.output for t in transports) == 1
            assert not any(b"HTTP/1.1 503 " in t.output for t in transports)
            assert any(b"retry-after: 1" in t.output.lower() for t in transports)
        finally:
            release.set()
            await asyncio.gather(*list(state.tasks))
            for protocol in protocols:
                protocol.connection_lost(None)
        assert peak == 8
        assert entered == 24
        assert sum(b"HTTP/1.1 200 " in t.output for t in transports) == 24

    asyncio.run(scenario())
