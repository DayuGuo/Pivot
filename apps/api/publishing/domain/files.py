"""Private, small UTF8 text CAS storage; caller owns all database authorization.

A storage key is derived only from content. Directory/file descriptors use no-follow
opens so untrusted keys or symlinks cannot turn a permitted download into another file.
This is text validation, not antivirus scanning or PDF/DOCX parsing.
"""

import base64
import binascii
import hashlib
import os
import re
import secrets
import stat
import unicodedata
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 1048576
MAX_BASE64 = 1398104
REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class FileValidationError(ValueError):
    """Fixed safe code; never contains raw file bytes, an OS path or a provider body."""


@dataclass(frozen=True)
class ValidatedFile:
    filename: str
    raw: bytes
    sha256: str
    byte_size: int
    media_type: str


def _validate_text(raw: bytes) -> None:
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        raise FileValidationError("invalid_file_size")
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeError:
        raise FileValidationError("file_must_be_utf8_text") from None
    if any(unicodedata.category(char) == "Cc" and char not in "\t\n\r" for char in text):
        raise FileValidationError("file_contains_control_characters")
    if any(char in "\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069" for char in text):
        raise FileValidationError("file_contains_direction_controls")


def validate_upload(filename: str, content_base64: str) -> ValidatedFile:
    if (
        not isinstance(filename, str)
        or not 1 <= len(filename) <= 255
        or filename != filename.strip()
        or any(char in filename for char in "/\\:\x00")
        or any(unicodedata.category(char) in {"Cc", "Cf"} for char in filename)
        or filename in {".", ".."}
        or filename.endswith((".", " "))
        or filename.split(".", 1)[0].upper()
        in {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *[f"COM{i}" for i in range(1, 10)],
            *[f"LPT{i}" for i in range(1, 10)],
        }
    ):
        raise FileValidationError("invalid_file_name")
    extension = Path(filename).suffix.casefold()
    if extension not in {".txt", ".md"}:
        raise FileValidationError("only_txt_and_md_supported")
    if not isinstance(content_base64, str) or not 4 <= len(content_base64) <= MAX_BASE64:
        raise FileValidationError("invalid_file_encoding")
    try:
        raw = base64.b64decode(content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise FileValidationError("invalid_file_encoding") from None
    if base64.b64encode(raw).decode("ascii") != content_base64:
        raise FileValidationError("invalid_file_encoding")
    _validate_text(raw)
    return ValidatedFile(
        filename=filename,
        raw=raw,
        sha256=hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        media_type="text/markdown" if extension == ".md" else "text/plain",
    )


def _root_path() -> Path:
    configured = os.environ.get("PUBLISHING_STORAGE_DIR")
    path = Path(configured) if configured else REPOSITORY_ROOT / "var" / "publishing-files"
    if not path.is_absolute():
        path = REPOSITORY_ROOT / path
    if ".." in path.parts or any("\x00" in part for part in path.parts):
        raise FileValidationError("invalid_storage_directory")
    return path


def _open_directory_path(path: Path, *, create: bool) -> int:
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in path.parts[1:]:
            if create:
                try:
                    os.mkdir(component, mode=0o700, dir_fd=descriptor)
                except FileExistsError:
                    pass
            next_descriptor = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _open_shard(root: int, prefix: str, *, create: bool) -> int:
    if create:
        try:
            os.mkdir(prefix, mode=0o700, dir_fd=root)
        except FileExistsError:
            pass
    return os.open(
        prefix,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        dir_fd=root,
    )


def _checked_read(shard: int, digest: str) -> bytes:
    descriptor = os.open(
        digest, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK, dir_fd=shard
    )
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_BYTES:
            raise FileValidationError("invalid_stored_file")
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or hashlib.sha256(raw).hexdigest() != digest:
        raise FileValidationError("stored_file_hash_mismatch")
    _validate_text(raw)
    return raw


def store_bytes(raw: bytes, sha256: str) -> str:
    _validate_text(raw)
    if (
        not isinstance(sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", sha256)
        or hashlib.sha256(raw).hexdigest() != sha256
    ):
        raise FileValidationError("file_hash_mismatch")
    root = shard = None
    temporary = None
    try:
        root = _open_directory_path(_root_path(), create=True)
        shard = _open_shard(root, sha256[:2], create=True)
        try:
            existing = _checked_read(shard, sha256)
        except FileNotFoundError:
            existing = None
        if existing is not None:
            return f"{sha256[:2]}/{sha256}"
        temporary = ".tmp-" + secrets.token_hex(16)
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            mode=0o600,
            dir_fd=shard,
        )
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            # Atomic publish without ever replacing a prior immutable CAS object.
            os.link(temporary, sha256, src_dir_fd=shard, dst_dir_fd=shard, follow_symlinks=False)
            os.fsync(shard)
        except FileExistsError:
            _checked_read(shard, sha256)
        return f"{sha256[:2]}/{sha256}"
    except FileValidationError:
        raise
    except OSError:
        raise FileValidationError("storage_write_failed") from None
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


def read_bytes(storage_key: str) -> bytes:
    match = (
        re.fullmatch(r"([0-9a-f]{2})/([0-9a-f]{64})", storage_key)
        if isinstance(storage_key, str)
        else None
    )
    if not match or match.group(1) != match.group(2)[:2]:
        raise FileValidationError("invalid_storage_key")
    root = shard = None
    try:
        root = _open_directory_path(_root_path(), create=False)
        shard = _open_shard(root, match.group(1), create=False)
        return _checked_read(shard, match.group(2))
    except FileValidationError:
        raise
    except OSError:
        raise FileValidationError("storage_read_failed") from None
    finally:
        if shard is not None:
            os.close(shard)
        if root is not None:
            os.close(root)
