"""Private, exact-version metadata export; no model calls or business writes."""

import json
from copy import deepcopy
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import Actor, get_actor
from . import dossier_access as access
from .author_links import author_issues
from .document_sources import attach_document, source_projection
from .dossier_evidence import leaf_fields
from .dossier_models import DossierCheck
from .dossier_schemas import DossierData, missing

router = APIRouter(prefix="/api/dossiers", tags=["private manuscript metadata export"])


def metadata_evidence(db, item, data, material, document):
    """Map only unchanged, unambiguous fields to their actual parsed original."""
    if document is None:
        return []
    text = material[1].decode("utf-8")
    result = []
    for path, value in leaf_fields(data):
        citation = {
            "kind": "metadata",
            "field_path": path,
            "start": 0,
            "end": len(value),
            "quote": value,
        }
        original = attach_document(citation, document, db, item).get("document")
        if original is None:
            continue
        start, end = original["source_start"], original["source_end"]
        if (
            type(start) is not int
            or type(end) is not int
            or not 0 <= start < end <= len(text)
            or text[start:end] != original["source_quote"]
            or original["sha256"] != document["sha256"]
            or original["origin_digest"] != document["origin_digest"]
        ):
            raise HTTPException(409, "元数据依据无法与此版本原文核对，未导出")
        result.append(
            {
                "field_path": path,
                "value": value,
                "quote": original["source_quote"],
                "start": start,
                "end": end,
                "locations": original["locations"],
                "original_sha256": document["sha256"],
                "origin_digest": document["origin_digest"],
            }
        )
    return result


@router.get("/{dossier_id}/versions/{version_id}/metadata-export")
def export_metadata(
    dossier_id: UUID,
    version_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    row = access.load(db, actor, str(dossier_id))
    item = access.version(db, row, str(version_id))
    material = access.file_content(db, item)
    if (
        access.snapshot_digest(
            item.data_json,
            material[0].sha256 if material else None,
            item.file_name,
            item.file_media_type,
        )
        != item.content_digest
    ):
        raise HTTPException(409, "版本来源摘要不一致，未导出")
    try:
        validated = DossierData.model_validate(item.data_json)
    except ValidationError:
        raise HTTPException(409, "版本元数据格式异常，未导出") from None
    document = source_projection(db, row, item)
    check = db.scalar(
        select(DossierCheck).where(
            DossierCheck.version_id == item.id,
            DossierCheck.dossier_id == row.id,
            DossierCheck.journal_id == row.journal_id,
        )
    )
    if check and check.content_digest != item.content_digest:
        raise HTTPException(409, "核对记录与版本摘要不一致，未导出")
    data = deepcopy(item.data_json)
    package = {
        "schema": "dossier-metadata-export.v1",
        "dossier_id": row.id,
        "version_id": item.id,
        "version_no": item.version_no,
        "content_digest": item.content_digest,
        "is_current": item.id == row.current_version_id,
        "data": data,
        "missing": missing(validated, material is not None),
        "author_issues": author_issues(data),
        "verified": check is not None,
        "verification": {
            "id": check.id,
            "by": check.checked_by,
            "at": check.checked_at.isoformat(),
        }
        if check
        else None,
        "file": {
            "filename": item.file_name,
            "media_type": item.file_media_type,
            "sha256": material[0].sha256,
            "byte_size": material[0].byte_size,
            "download_url": f"/api/dossiers/{row.id}/versions/{item.id}/file",
        }
        if material
        else None,
        "document": {
            key: document[key]
            for key in (
                "import_id",
                "filename",
                "media_type",
                "sha256",
                "byte_size",
                "download_url",
                "parser",
                "origin_digest",
                "warnings",
                "approval",
            )
        }
        if document
        else None,
        "field_sources": metadata_evidence(db, item, data, material, document),
    }
    # Recheck the current session/role/ownership after all source work, before bytes leave.
    row = access.load(db, actor, row.id)
    package["is_current"] = item.id == row.current_version_id
    return Response(
        json.dumps(package, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="pivot-metadata-{item.id}.json"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
