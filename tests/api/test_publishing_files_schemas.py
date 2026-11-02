"""Pure DTO and storage safety tests; no publishing DB mutations or model calls."""

import base64
import hashlib
import os
import stat
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from apps.api.publishing.domain.files import (
    MAX_BYTES,
    FileValidationError,
    read_bytes,
    store_bytes,
    validate_upload,
)
from apps.api.publishing.domain.schemas import (
    AuthorInput,
    DeclarationsInput,
    FileUpload,
    IntakeCandidates,
    IntakeData,
    missing_requirements,
)


def encoded(raw=b"Synthetic text\n"):
    return base64.b64encode(raw).decode()


def ready(**extra):
    data = {
        "title": "A synthetic publishing study",
        "abstract": "Synthetic public test material for verifying publication workflows. " * 2,
        "keywords": ["workflow"],
        "authors": [
            {"name": "Test Author", "email": "author@publishing.test", "corresponding": True}
        ],
        "declarations": {
            "originality": True,
            "copyright": True,
            "competing_interests": "none",
            "ethics": "not_applicable",
        },
    }
    return IntakeData.model_validate({**data, **extra})


def missing_fields(data, purposes=None):
    return {item["field"] for item in missing_requirements(data, purposes or set())}


def test_empty_draft_is_saveable_without_inventing_declarations_or_authority():
    draft = IntakeData()
    assert draft.authors == [] and draft.title == ""
    assert draft.declarations == DeclarationsInput()
    assert not draft.declarations.originality and not draft.declarations.copyright
    assert draft.declarations.competing_interests == "unanswered"
    assert draft.declarations.ethics == "unanswered"
    assert {
        "title",
        "abstract",
        "keywords",
        "authors",
        "authors.corresponding",
        "files.manuscript",
        "files.blinded_manuscript",
        "declarations.originality",
        "declarations.copyright",
        "declarations.competing_interests",
        "declarations.ethics",
    } <= missing_fields(draft)


def test_complete_author_intake_has_no_missing_requirements_and_independent_defaults():
    data = ready()
    assert missing_requirements(data, {"manuscript", "blinded_manuscript"}) == []
    first, second = IntakeData(), IntakeData()
    first.keywords.append("not shared")
    first.declarations.originality = True
    assert not second.keywords and not second.declarations.originality


@pytest.mark.parametrize(
    "model,payload",
    [
        (AuthorInput, {"linked_user_id": "another-account"}),
        (AuthorInput, {"role": "chief_editor"}),
        (IntakeData, {"journal_id": "other-journal"}),
        (IntakeData, {"permissions": ["confirm"]}),
        (IntakeCandidates, {"declarations": {"originality": True}}),
        (IntakeCandidates, {"owner_id": "other-account"}),
        (IntakeCandidates, {"authors": [{"linked_user_id": "authority"}]}),
        (DeclarationsInput, {"originality": "true"}),
        (DeclarationsInput, {"copyright": 1}),
        (AuthorInput, {"corresponding": "false"}),
        (IntakeData, {"title": 123}),
        (
            FileUpload,
            {
                "filename": "paper.txt",
                "content_base64": encoded(),
                "purpose": "proof",
                "storage_key": "unsafe",
            },
        ),
    ],
)
def test_strict_dtos_reject_authority_extras_and_coerced_types(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_candidates_only_contain_proposed_metadata_and_save_missing_fields():
    candidate = IntakeCandidates(title="  Synthetic title  ", authors=[AuthorInput(name="待补充")])
    assert candidate.model_dump(exclude_none=True) == {
        "title": "Synthetic title",
        "authors": [
            {
                "name": "待补充",
                "email": "",
                "affiliations": [],
                "corresponding": False,
                "contributions": [],
            }
        ],
    }
    assert missing_fields(IntakeData.model_validate(candidate.model_dump(exclude_none=True))) >= {
        "authors.0.email",
        "authors.corresponding",
    }


@pytest.mark.parametrize(
    "field,value",
    [
        ("title", "x" * 501),
        ("abstract", "x" * 12001),
        ("keywords", ["x"] * 13),
        ("keywords", ["x" * 81]),
        ("authors", [{}] * 21),
        ("language", "fr"),
        ("article_type", "unknown"),
        ("funding_statement", "x" * 4001),
    ],
)
def test_intake_bounds_prevent_unbounded_metadata(field, value):
    with pytest.raises(ValidationError):
        IntakeData.model_validate({field: value})


@pytest.mark.parametrize(
    "value,normalized",
    [
        (None, None),
        ("", None),
        ("   ", None),
        ("0000-0002-1825-0097", "0000-0002-1825-0097"),
        ("https://orcid.org/0000-0002-1694-233x", "0000-0002-1694-233X"),
        ("0000-0000-0000-0000", "0000-0000-0000-0000"),
    ],
)
def test_orcid_normalizes_format_without_claiming_identity_or_checksum(value, normalized):
    assert AuthorInput(orcid=value).orcid == normalized


@pytest.mark.parametrize(
    "value",
    [
        "https://untrusted.example/0000-0002-1825-0097",
        "0000000218250097",
        "0000-0002-1825-00ZZ",
        "００００-０００２-１８２５-００９７",
        123,
    ],
)
def test_orcid_rejects_other_urls_and_invalid_syntax(value):
    with pytest.raises(ValidationError):
        AuthorInput(orcid=value)


@pytest.mark.parametrize(
    "email",
    [
        "",
        "bad",
        "a@@b.test",
        ".a@b.test",
        "a..b@c.test",
        "a@-bad.test",
        "a@bad_.test",
        "a@localhost",
        "a\n@b.test",
    ],
)
def test_email_errors_are_reported_at_confirmation_gate_not_lost_during_drafting(email):
    draft = ready(authors=[{"name": "Draft Author", "email": email, "corresponding": True}])
    assert "authors.0.email" in missing_fields(draft)


@pytest.mark.parametrize("email", ["author+test@publishing.test", "author@研究.测试"])
def test_submission_gate_accepts_normal_mailbox_syntax_without_network_verification(email):
    assert "authors.0.email" not in missing_fields(
        ready(authors=[{"name": "作者", "email": email, "corresponding": True}])
    )


def test_author_names_and_exactly_one_corresponding_author_are_required():
    authors = [
        {"name": "", "email": "first@publishing.test", "corresponding": True},
        {"name": "Second", "email": "second@publishing.test", "corresponding": True},
    ]
    missing = missing_fields(ready(authors=authors))
    assert {"authors.0.name", "authors.corresponding"} <= missing
    assert "files.blinded_manuscript" in missing_fields(ready(), {"manuscript"})


def test_positive_declarations_require_own_text_and_checks_do_not_mutate_draft():
    data = ready(
        declarations={
            "originality": True,
            "copyright": True,
            "competing_interests": "declared",
            "ethics": "approved",
        }
    )
    before = data.model_dump()
    missing = missing_fields(data, {"manuscript", "blinded_manuscript"})
    assert missing == {"declarations.competing_interests_text", "declarations.ethics_reference"}
    assert data.model_dump() == before
    data.declarations.competing_interests_text = "A synthetic declared funding relationship"
    data.declarations.ethics_reference = "Synthetic approval ref TEST-001"
    assert not missing_requirements(data, {"manuscript", "blinded_manuscript"})


@pytest.mark.parametrize(
    "filename,raw,media",
    [
        ("稿件.txt", "合成研究\n第二行".encode(), "text/plain"),
        ("paper.MD", b"# Synthetic paper\n\tcontent", "text/markdown"),
    ],
)
def test_actual_upload_bytes_are_validated_and_hashed(filename, raw, media):
    result = validate_upload(filename, encoded(raw))
    assert result.filename == filename and result.raw == raw
    assert result.sha256 == hashlib.sha256(raw).hexdigest()
    assert result.byte_size == len(raw) and result.media_type == media


@pytest.mark.parametrize(
    "filename",
    [
        "../paper.txt",
        "folder/paper.txt",
        "folder\\paper.txt",
        "/paper.txt",
        "C:paper.txt",
        "paper.txt\x00",
        "paper\n.txt",
        " paper.txt",
        "paper.txt ",
        "CON.txt",
        ".",
        "..",
        "a\u202etxt.txt",
    ],
)
def test_upload_names_cannot_supply_paths_or_control_sequences(filename):
    with pytest.raises(FileValidationError):
        validate_upload(filename, encoded())


@pytest.mark.parametrize("filename", ["paper.pdf", "paper.docx", "paper.html", "paper.exe", ".txt"])
def test_unsupported_formats_are_not_misrepresented_as_parsed_or_scanned(filename):
    with pytest.raises(FileValidationError):
        validate_upload(filename, encoded())


@pytest.mark.parametrize(
    "content",
    ["", "####", "YQ===", "YQ==\n", "Y Q==", "data:text/plain;base64,YQ==", "YR==", "文字"],
)
def test_base64_is_strict_and_canonical(content):
    with pytest.raises(FileValidationError):
        validate_upload("paper.txt", content)


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"\xff\xfe",
        b"text\x00binary",
        b"\x1b[31munsafe",
        b"\x7f",
        "text\u0085control".encode(),
        "text\u202espoof".encode(),
    ],
)
def test_text_only_boundary_rejects_empty_binary_and_terminal_or_direction_controls(raw):
    with pytest.raises(FileValidationError):
        validate_upload("paper.txt", encoded(raw))


def test_actual_decoded_size_not_only_base64_length_is_bounded():
    raw = b"x" * MAX_BYTES
    assert validate_upload("max.txt", encoded(raw)).byte_size == MAX_BYTES
    with pytest.raises(FileValidationError):
        validate_upload("too-large.txt", encoded(raw + b"x"))


@pytest.fixture
def storage(tmp_path, monkeypatch):
    root = tmp_path / "cas"
    monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(root))
    return root


def test_storage_roundtrip_is_private_immutable_and_deduplicated(storage):
    upload = validate_upload("paper.txt", encoded())
    key = store_bytes(upload.raw, upload.sha256)
    target = storage / key
    assert key == f"{upload.sha256[:2]}/{upload.sha256}"
    before = target.stat()
    assert stat.S_IMODE(before.st_mode) == 0o600
    assert read_bytes(key) == upload.raw
    assert store_bytes(upload.raw, upload.sha256) == key
    assert target.stat().st_ino == before.st_ino
    assert not list(target.parent.glob(".tmp-*"))


def test_wrong_hash_never_creates_storage(storage):
    with pytest.raises(FileValidationError, match="file_hash_mismatch"):
        store_bytes(b"text", "0" * 64)
    assert not storage.exists()


@pytest.mark.parametrize(
    "key",
    [
        "../secret",
        "/etc/passwd",
        "ff/" + "0" * 64,
        "00/" + "A" * 64,
        "00/" + "0" * 64 + "/more",
        "00\\" + "0" * 64,
        "00/../../secret",
    ],
)
def test_storage_keys_never_become_arbitrary_paths(storage, key):
    with pytest.raises(FileValidationError, match="invalid_storage_key"):
        read_bytes(key)
    assert not storage.exists()


def test_corrupt_existing_content_is_not_read_or_silently_overwritten(storage):
    raw = b"Synthetic private content"
    digest = hashlib.sha256(raw).hexdigest()
    key = store_bytes(raw, digest)
    target = storage / key
    target.write_bytes(b"corrupt")
    for action in (lambda: read_bytes(key), lambda: store_bytes(raw, digest)):
        with pytest.raises(FileValidationError, match="stored_file_hash_mismatch"):
            action()
    assert target.read_bytes() == b"corrupt"


def test_symlink_root_and_parent_are_rejected(tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    link = tmp_path / "symlink"
    link.symlink_to(outside, target_is_directory=True)
    for root in (link, link / "child"):
        monkeypatch.setenv("PUBLISHING_STORAGE_DIR", str(root))
        raw = b"text"
        digest = hashlib.sha256(raw).hexdigest()
        with pytest.raises(FileValidationError):
            store_bytes(raw, digest)
    assert list(outside.iterdir()) == []


def test_symlink_shard_is_rejected_without_touching_external_directory(storage, tmp_path):
    raw = b"text"
    digest = hashlib.sha256(raw).hexdigest()
    outside = tmp_path / "outside"
    outside.mkdir()
    storage.mkdir()
    (storage / digest[:2]).symlink_to(outside, target_is_directory=True)
    with pytest.raises(FileValidationError):
        store_bytes(raw, digest)
    with pytest.raises(FileValidationError):
        read_bytes(f"{digest[:2]}/{digest}")
    assert list(outside.iterdir()) == []


def test_symlink_object_is_rejected_even_if_external_hash_matches(storage, tmp_path):
    raw = b"external private text"
    digest = hashlib.sha256(raw).hexdigest()
    outside = tmp_path / "outside.txt"
    outside.write_bytes(raw)
    target = storage / digest[:2]
    target.mkdir(parents=True)
    (target / digest).symlink_to(outside)
    for action in (lambda: read_bytes(f"{digest[:2]}/{digest}"), lambda: store_bytes(raw, digest)):
        with pytest.raises(FileValidationError):
            action()
    assert outside.read_bytes() == raw


def test_fifo_storage_object_cannot_block_a_read(storage):
    digest = hashlib.sha256(b"text").hexdigest()
    directory = storage / digest[:2]
    directory.mkdir(parents=True)
    os.mkfifo(directory / digest)
    with pytest.raises(FileValidationError, match="invalid_stored_file"):
        read_bytes(f"{digest[:2]}/{digest}")


def test_failed_atomic_publish_leaves_no_partial_object_or_temporary_file(storage, monkeypatch):
    raw = b"Synthetic text"
    digest = hashlib.sha256(raw).hexdigest()

    def failed_link(*args, **kwargs):
        raise OSError("sensitive filesystem error")

    monkeypatch.setattr(os, "link", failed_link)
    with pytest.raises(FileValidationError, match="^storage_write_failed$") as error:
        store_bytes(raw, digest)
    assert "sensitive" not in str(error.value)
    assert list((storage / digest[:2]).iterdir()) == []


def test_concurrent_identical_writers_publish_one_complete_object(storage):
    raw = ("合成数据\n" * 100).encode()
    digest = hashlib.sha256(raw).hexdigest()
    with ThreadPoolExecutor(max_workers=8) as executor:
        keys = list(executor.map(lambda _: store_bytes(raw, digest), range(16)))
    assert len(set(keys)) == 1 and read_bytes(keys[0]) == raw
    assert [p.name for p in (storage / digest[:2]).iterdir()] == [digest]
