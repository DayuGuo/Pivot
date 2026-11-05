"""Shared source projection for legacy downloads and registered evaluation packages."""

from fastapi import HTTPException

from . import dossier_access as access
from .claim_evaluation_package import InvalidEvaluationSource, citation_projection
from .claim_review_sources import answer_source
from .document_sources import attach_document, source_projection


def evaluation_material(db, actor, dossier_id, answer_id):
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
    entries, targets = [], []
    try:
        for bucket in ("claims", "withheld_claims"):
            claims = answer.result_json.get(bucket, [])
            if not isinstance(claims, list) or len(claims) > 6:
                raise InvalidEvaluationSource("claim_shape")
            for index, claim in enumerate(claims):
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
                targets.append({"bucket": bucket, "index": index, "claim": claim})
        if not entries:
            raise InvalidEvaluationSource("no_claims")
    except InvalidEvaluationSource:
        raise HTTPException(
            409, "结论或引用无法与该历史版本逐字核对，未生成评价包；请重新提问或联系负责人检查"
        ) from None
    return row, item, answer, source, entries, targets
