"""Authenticated, read-only export for independent source-based evaluation."""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import Actor, get_actor
from . import dossier_access as access
from .claim_evaluation_package import (
    InvalidEvaluationSource,
    citation_projection,
    package_projection,
)
from .claim_review_sources import answer_source
from .document_sources import attach_document, source_projection

router = APIRouter(prefix="/api/dossiers", tags=["independent evidence evaluation"])


@router.get("/{dossier_id}/answers/{answer_id}/evaluation-package")
def evaluation_package(
    dossier_id: UUID,
    answer_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    row, item, answer = answer_source(db, actor, dossier_id, answer_id)
    material = access.file_content(db, item)
    if not material:
        raise HTTPException(409, "请先上传完整正文；仅有元数据不能生成独立评价包")
    text = material[1].decode("utf-8")
    document = source_projection(db, row, item)
    source = {
        "version_id": item.id,
        "version_no": item.version_no,
        "content_digest": item.content_digest,
        "data": item.data_json,
        "text": text,
        "file_sha256": material[0].sha256,
        "file_name": item.file_name,
        "file_media_type": item.file_media_type,
    }
    if document:
        source["document"] = {
            k: document[k]
            for k in ("sha256", "filename", "media_type", "segments", "warnings", "download_url")
        }
    entries = []
    try:
        for bucket in ("claims", "withheld_claims"):
            claims = answer.result_json.get(bucket, [])
            if not isinstance(claims, list) or len(claims) > 6:
                raise InvalidEvaluationSource("claim_shape")
            for claim in claims:
                if (
                    not isinstance(claim, dict)
                    or not isinstance(claim.get("text"), str)
                    or not claim["text"].strip()
                    or not isinstance(claim.get("citations"), list)
                    or not 1 <= len(claim["citations"]) <= 6
                ):
                    raise InvalidEvaluationSource("claim_shape")
                citations = []
                for original in claim["citations"]:
                    projected = citation_projection(
                        original, version=source, text=text, file_sha256=material[0].sha256
                    )
                    if original.get("document"):
                        canonical = attach_document(
                            original | {"document": None}, document, db, item
                        )
                        if canonical.get("document") != original["document"]:
                            raise InvalidEvaluationSource("document_location")
                        projected["document"] = {
                            k: canonical["document"][k]
                            for k in (
                                "sha256",
                                "source_start",
                                "source_end",
                                "source_quote",
                                "locations",
                            )
                        }
                    citations.append(projected)
                entries.append({"text": claim["text"], "citations": citations})
        if not entries:
            raise InvalidEvaluationSource("no_claims")
    except InvalidEvaluationSource:
        raise HTTPException(
            409, "结论或引用无法与该历史版本逐字核对，未生成评价包；请重新提问或联系负责人检查"
        ) from None
    # No labels, answer wrapper, question, telemetry or previous feedback cross this boundary.
    package = package_projection(source, entries)
    access.load(db, actor, row.id)
    return Response(
        json.dumps(package, ensure_ascii=False, indent=2),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="pivot-evaluation-{package["package_id"]}.json"',
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
