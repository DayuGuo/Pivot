"""Offline virtual-runner filesystem tests; never change this host's /etc or privileges."""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ci_apt_fallback", ROOT / "scripts/ci-ubuntu-apt-fallback.py"
)
fallback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fallback)


@pytest.fixture
def runner(tmp_path):
    for name in (
        "usr/lib",
        "etc/apt/apt.conf.d",
        "etc/apt/sources.list.d",
        "home/runner/work/_temp",
    ):
        (tmp_path / name).mkdir(parents=True, exist_ok=True)
    (tmp_path / "usr/lib/os-release").write_text(
        'ID=ubuntu\nVERSION_ID="24.04"\nUBUNTU_CODENAME=noble\n'
    )
    # Real Ubuntu uses this link. It is not followed; only the fixed canonical
    # /usr/lib/os-release regular file supplies the guarded OS identity.
    (tmp_path / "etc/os-release").symlink_to("../usr/lib/os-release")
    mirrors = "".join(
        f"{url}\tpriority:{priority}\n" for url, priority in fallback.INITIAL_MIRRORS
    ).encode()
    (tmp_path / fallback.MIRROR_PATH).write_bytes(mirrors)
    trust = b"URIs: mirror+file:/etc/apt/apt-mirrors.txt\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n"
    (tmp_path / "etc/apt/sources.list.d/ubuntu.sources").write_bytes(trust)
    for path in (
        tmp_path / "usr/lib/os-release",
        tmp_path / fallback.MIRROR_PATH,
        tmp_path / "etc/apt/sources.list.d/ubuntu.sources",
    ):
        path.chmod(0o644)
    environment = {**fallback.SAFE_CONTEXT, "RUNNER_TEMP": "/home/runner/work/_temp"}
    options = {
        "root": tmp_path,
        "environ": environment,
        "uid": 0,
        "system": "Linux",
        "machine": "x86_64",
    }
    return tmp_path, options, mirrors, trust


def backups(root):
    return list((root / "home/runner/work/_temp").glob("pivot-apt-backup-*"))


def test_official_priority_mirrors_and_private_backups_preserve_signature_configuration(runner):
    root, options, original, trust = runner
    assert fallback.apply_fallback(**options) == 2
    assert (root / fallback.MIRROR_PATH).read_bytes() == fallback.MIRROR_TEXT
    assert (root / fallback.NETWORK_PATH).read_bytes() == fallback.NETWORK_TEXT
    assert (root / "etc/apt/sources.list.d/ubuntu.sources").read_bytes() == trust
    directories = backups(root)
    assert len(directories) == 1
    assert directories[0].stat().st_mode & 0o777 == 0o700
    assert (directories[0] / "original-0.bin").read_bytes() == original
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in directories[0].iterdir())
    assert not (root / "artifacts").exists()
    assert fallback.apply_fallback(**options) == 0
    assert (root / fallback.MIRROR_PATH).read_bytes() == fallback.MIRROR_TEXT


@pytest.mark.parametrize(
    "field,value",
    [
        ("GITHUB_ACTIONS", "false"),
        ("RUNNER_OS", "Windows"),
        ("RUNNER_ARCH", "ARM64"),
        ("RUNNER_ENVIRONMENT", "self-hosted"),
        ("RUNNER_TEMP", "/tmp/artifacts"),
    ],
)
def test_only_ephemeral_github_hosted_context_can_change_sources(runner, field, value):
    root, options, original, _ = runner
    options["environ"][field] = value
    with pytest.raises(fallback.FallbackError):
        fallback.apply_fallback(**options)
    assert (root / fallback.MIRROR_PATH).read_bytes() == original
    assert not backups(root)


@pytest.mark.parametrize(
    "field,value", [("uid", 1000), ("system", "Darwin"), ("machine", "aarch64")]
)
def test_actual_host_and_root_guards_are_independent_of_environment(runner, field, value):
    root, options, original, _ = runner
    options[field] = value
    with pytest.raises(fallback.FallbackError):
        fallback.apply_fallback(**options)
    assert (root / fallback.MIRROR_PATH).read_bytes() == original
    assert not backups(root)


def test_other_ubuntu_release_is_rejected_before_configuration_changes(runner):
    root, options, original, _ = runner
    (root / "usr/lib/os-release").write_text('ID=ubuntu\nVERSION_ID="26.04"\n')
    with pytest.raises(fallback.FallbackError):
        fallback.apply_fallback(**options)
    assert (root / fallback.MIRROR_PATH).read_bytes() == original
    assert not backups(root)


@pytest.mark.parametrize(
    "content",
    [
        b"http://user:password@azure.archive.ubuntu.com/ubuntu/\tpriority:1\n",
        b"https://example.test/ubuntu/\tpriority:1\n",
        b"https://archive.ubuntu.com/ubuntu/?token=synthetic\tpriority:1\n",
        b"https://archive.ubuntu.com/ubuntu/\tpriority:4\n",
        b"https://archive.ubuntu.com/ubuntu/\n",
    ],
)
def test_unexpected_or_credential_sources_are_refused_without_backup_or_content_diagnostics(
    runner, content
):
    root, options, _, _ = runner
    path = root / fallback.MIRROR_PATH
    path.write_bytes(content)
    with pytest.raises(fallback.FallbackError) as error:
        fallback.apply_fallback(**options)
    assert "password" not in str(error.value) and "example.test" not in str(error.value)
    assert path.read_bytes() == content
    assert not backups(root)


@pytest.mark.parametrize("target", [fallback.MIRROR_PATH, fallback.NETWORK_PATH])
def test_apt_symlinks_cannot_redirect_reads_or_writes(runner, target):
    root, options, _, _ = runner
    outside = root / "outside.txt"
    outside.write_text("synthetic untouched outside file")
    path = root / target
    path.unlink(missing_ok=True)
    path.symlink_to(outside)
    with pytest.raises(fallback.FallbackError):
        fallback.apply_fallback(**options)
    assert outside.read_text() == "synthetic untouched outside file"
    assert not backups(root)


def test_backup_parent_symlink_chain_is_refused(runner):
    root, options, original, _ = runner
    temporary = root / "home/runner/work/_temp"
    temporary.rmdir()
    outside = root / "outside-backups"
    outside.mkdir()
    temporary.symlink_to(outside, target_is_directory=True)
    with pytest.raises(fallback.FallbackError):
        fallback.apply_fallback(**options)
    assert list(outside.iterdir()) == []
    assert (root / fallback.MIRROR_PATH).read_bytes() == original


def test_existing_unowned_network_override_is_not_replaced(runner):
    root, options, original, _ = runner
    path = root / fallback.NETWORK_PATH
    path.write_text('Acquire::https::Verify-Peer "false";\n')
    path.chmod(0o644)
    with pytest.raises(fallback.FallbackError):
        fallback.apply_fallback(**options)
    assert path.read_text() == 'Acquire::https::Verify-Peer "false";\n'
    assert (root / fallback.MIRROR_PATH).read_bytes() == original
    assert not backups(root)


def test_partial_write_failure_rolls_back_and_keeps_private_backup(runner, monkeypatch):
    root, options, original, trust = runner
    write = fallback.write_atomic

    def fail_network(path, raw):
        if path == root / fallback.NETWORK_PATH:
            raise OSError("synthetic write failure")
        write(path, raw)

    monkeypatch.setattr(fallback, "write_atomic", fail_network)
    with pytest.raises(OSError):
        fallback.apply_fallback(**options)
    assert (root / fallback.MIRROR_PATH).read_bytes() == original
    assert not (root / fallback.NETWORK_PATH).exists()
    assert (root / "etc/apt/sources.list.d/ubuntu.sources").read_bytes() == trust
    assert len(backups(root)) == 1
