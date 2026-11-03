"""Small private binary originals; kept separate from the text-only publishing CAS."""

import hashlib
import os
import re
import secrets
import stat

from .files import FileValidationError, _open_directory_path, _open_shard, _root_path

MAX_BYTES = 5 * 1024 * 1024


def _read(shard, sha):
    descriptor = os.open(
        sha, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=shard
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_BYTES:
            raise FileValidationError("invalid_original_storage")
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) != info.st_size or hashlib.sha256(raw).hexdigest() != sha:
        raise FileValidationError("original_hash_mismatch")
    return raw


def read_original(key):
    match = re.fullmatch(r"([0-9a-f]{2})/([0-9a-f]{64})", key) if isinstance(key, str) else None
    if not match or match[1] != match[2][:2]:
        raise FileValidationError("invalid_original_storage_key")
    root = shard = None
    try:
        root = _open_directory_path(_root_path() / "document-originals", create=False)
        shard = _open_shard(root, match[1], create=False)
        return _read(shard, match[2])
    except OSError:
        raise FileValidationError("original_read_failed") from None
    finally:
        if shard is not None:
            os.close(shard)
        if root is not None:
            os.close(root)


def store_original(raw):
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise FileValidationError("invalid_original_size")
    sha = hashlib.sha256(raw).hexdigest()
    root = shard = None
    temporary = None
    try:
        root = _open_directory_path(_root_path() / "document-originals", create=True)
        shard = _open_shard(root, sha[:2], create=True)
        try:
            _read(shard, sha)
            return f"{sha[:2]}/{sha}"
        except FileNotFoundError:
            pass
        temporary = ".tmp-" + secrets.token_hex(16)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            mode=0o600,
            dir_fd=shard,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, sha, src_dir_fd=shard, dst_dir_fd=shard, follow_symlinks=False)
            os.fsync(shard)
        except FileExistsError:
            _read(shard, sha)
        return f"{sha[:2]}/{sha}"
    except OSError:
        raise FileValidationError("original_write_failed") from None
    finally:
        if temporary is not None and shard is not None:
            try:
                os.unlink(temporary, dir_fd=shard)
            except OSError:
                pass
        if shard is not None:
            os.close(shard)
        if root is not None:
            os.close(root)
