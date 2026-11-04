"""Immutable import provenance, integrity and quote locations; no routes/provider calls."""

import hashlib

from fastapi import HTTPException

from .core import digest
from .document_models import DocumentApproval, DocumentImport, DocumentSource
from .document_store import read_original
from .dossier_access import file_content
from .dossier_evidence import leaf_fields
from .files import FileValidationError


def import_digest(item):
    return digest(
        {
            "schema": "document_import.v1",
            "dossier_id": item.dossier_id,
            "base_version_id": item.base_version_id,
            "base_revision": item.base_revision,
            "filename": item.filename,
            "media_type": item.media_type,
            "byte_size": item.byte_size,
            "sha256": item.sha256,
            "extraction": item.extraction_json,
            "proposed_data": item.proposed_data,
            "field_sources": item.field_sources,
            "metadata_provider": item.metadata_provider,
            "metadata_model": item.metadata_model,
        }
    )


def approval_digest(item, data, version_digest):
    return digest(
        {
            "schema": "document_approval.v1",
            "import_digest": item.digest,
            "data": data,
            "version_digest": version_digest,
        }
    )


def origin_digest(item, approval, version):
    return digest(
        {
            "schema": "document_origin.v1",
            "import_digest": item.digest,
            "approval_digest": approval.digest,
            "version_digest": version.content_digest,
            "sha256": item.sha256,
        }
    )


def verify_import(item):
    try:
        raw = read_original(item.storage_key)
    except FileValidationError:
        raise HTTPException(409, "原文件完整性检查失败，请重新导入") from None
    if (
        len(raw) != item.byte_size
        or hashlib.sha256(raw).hexdigest() != item.sha256
        or import_digest(item) != item.digest
    ):
        raise HTTPException(409, "导入快照或原文件已变化，请重新导入")
    extraction = item.extraction_json
    text = extraction["text"]
    if hashlib.sha256(text.encode()).hexdigest() != extraction["sha256"]:
        raise HTTPException(409, "提取全文完整性检查失败")
    return raw


def source_projection(db, row, version):
    link = db.get(DocumentSource, version.id)
    if link is None:
        return None
    item = db.get(DocumentImport, link.import_id)
    approval = db.get(DocumentApproval, link.approval_id)
    if (
        not item
        or not approval
        or item.dossier_id != row.id
        or item.journal_id != row.journal_id
        or approval.import_id != item.id
    ):
        raise HTTPException(409, "原文件关联不完整")
    verify_import(item)
    material = file_content(db, version)
    if (
        not material
        or material[0].sha256 != item.extraction_json["sha256"]
        or material[1].decode() != item.extraction_json["text"]
    ):
        raise HTTPException(409, "提取全文与原文件关联不一致")
    expected = origin_digest(item, approval, version)
    if link.origin_digest != expected:
        raise HTTPException(409, "原文来源摘要不一致")
    return {
        "import_id": item.id,
        "filename": item.filename,
        "media_type": item.media_type,
        "sha256": item.sha256,
        "byte_size": item.byte_size,
        "download_url": f"/api/dossiers/{row.id}/imports/{item.id}/file",
        "parser": item.extraction_json["parser"],
        "origin_digest": expected,
        "segments": item.extraction_json["segments"],
        "warnings": item.extraction_json["warnings"],
        "approval": {
            "id": approval.id,
            "by": approval.reviewer_id,
            "at": approval.created_at.isoformat(),
        },
    }


def inherit_source(db, row, old, new):
    previous = db.get(DocumentSource, old.id)
    if previous is None:
        return
    source_projection(db, row, old)
    item = db.get(DocumentImport, previous.import_id)
    approval = db.get(DocumentApproval, previous.approval_id)
    db.add(
        DocumentSource(
            version_id=new.id,
            dossier_id=row.id,
            journal_id=row.journal_id,
            import_id=item.id,
            approval_id=approval.id,
            origin_digest=origin_digest(item, approval, new),
        )
    )
    db.flush()


def attach_document(citation, document, db=None, version=None):
    if not document:
        return citation
    start, end = citation["start"], citation["end"]
    source_quote = citation["quote"]
    if citation["kind"] == "metadata":
        if db is None or version is None:
            return citation
        item = db.get(DocumentImport, document["import_id"])
        source_path = citation["field_path"]
        if source_path.startswith("authors."):
            parts = source_path.split(".")
            index = int(parts[1])
            old_authors = item.proposed_data.get("authors", [])
            new_authors = version.data_json.get("authors", [])
            if index >= len(new_authors):
                return citation
            name = new_authors[index]["name"]
            old_matches = [i for i, author in enumerate(old_authors) if author["name"] == name]
            if (
                not name
                or len(old_matches) != 1
                or sum(a["name"] == name for a in new_authors) != 1
            ):
                # Duplicate names are not a person identifier; never guess by slot.
                return citation
            original_index = old_matches[0]
            parts[1] = str(original_index)
            if len(parts) == 4 and parts[2] in {"affiliations", "contributions"}:
                values = old_authors[original_index].get(parts[2], [])
                current_value = dict(leaf_fields(version.data_json)).get(citation["field_path"])
                matches = [i for i, value in enumerate(values) if value == current_value]
                if len(matches) != 1:
                    return citation
                parts[3] = str(matches[0])
            source_path = ".".join(parts)
        source = next(
            (
                s
                for s in item.field_sources
                if s["field_path"] == source_path
                and s["value"] == dict(leaf_fields(version.data_json)).get(citation["field_path"])
            ),
            None,
        )
        if source is None:
            return citation
        start, end = source["start"], source["end"]
        source_quote = source["quote"]
    locations = [
        {
            "kind": s["kind"],
            "number": s["number"],
            "start": max(start, s["start"]),
            "end": min(end, s["end"]),
        }
        for s in document["segments"]
        if start < s["end"] and end > s["start"]
    ]
    if not locations:
        return citation
    return {
        **citation,
        "document": {
            "origin_digest": document["origin_digest"],
            "sha256": document["sha256"],
            "filename": document["filename"],
            "media_type": document["media_type"],
            "download_url": document["download_url"],
            "locations": locations,
            "source_start": start,
            "source_end": end,
            "source_quote": source_quote,
        },
    }
