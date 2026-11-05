"""Rebuild private comparison sources from exact authorised versions and original bytes."""

import hashlib
from copy import deepcopy

from fastapi import HTTPException

from . import dossier_access as access
from .core import digest
from .document_sources import source_projection
from .dossier_evidence import credential_like


def material_input(body):
    return body.model_dump(
        mode="json", exclude={"request_id", "expected_revision", "authorized_material"}
    )


def version_material(db, row, version_id, kind, complete):
    item = access.version(db, row, version_id)
    material = access.file_content(db, item)
    if not material:
        raise HTTPException(409, "原稿和修订稿都需要实际保存的正文文件")
    blob, raw = material
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(409, "修回核对需要经过提取的UTF-8正文") from None
    if not text.strip():
        raise HTTPException(409, "修回正文不能为空")
    actual = access.snapshot_digest(
        item.data_json, blob.sha256, item.file_name, item.file_media_type
    )
    if actual != item.content_digest:
        raise HTTPException(409, "稿件版本摘要与实际正文不一致")
    document = source_projection(db, row, item)
    download = f"/api/dossiers/{row.id}/versions/{item.id}/file"
    # This internal mapping is real Unicode text, never an invented PDF/Word page.
    origin = {
        "selection_start": 0,
        "selection_end": len(text),
        "source_complete": complete,
        "filename": document["filename"] if document else item.file_name,
        "sha256": document["sha256"] if document else blob.sha256,
        "download_url": document["download_url"] if document else download,
        "segments": document["segments"]
        if document
        else [{"kind": "text", "number": 1, "start": 0, "end": len(text), "text": text}],
    }
    return item, {
        "kind": kind,
        "file_id": blob.id,
        "version_id": item.id,
        "version_no": item.version_no,
        "sha256": blob.sha256,
        "text": text,
        "origin": origin,
        "binary_origin": document is not None,
        "download_url": download,
        "content_digest": item.content_digest,
        "filename": item.file_name,
    }


def source(db, actor, dossier_id, materials, check_id, revision, *, current=False):
    row = access.load(db, actor, dossier_id)
    if current:
        access.current(row, revision, materials["revised_version_id"])
    base, old = version_material(
        db, row, materials["base_version_id"], "base", materials["base_complete"]
    )
    revised, new = version_material(
        db, row, materials["revised_version_id"], "revised", materials["revised_complete"]
    )
    if base.version_no >= revised.version_no:
        raise HTTPException(422, "原稿必须是同一资料中更早的不同版本")
    response = materials["response_text"]
    response_sha = hashlib.sha256(response.encode()).hexdigest()
    files = {
        "base": old,
        "revised": new,
        "response": {
            "kind": "response",
            "file_id": f"pasted-response:{check_id}",
            "version_id": revised.id,
            "version_no": revised.version_no,
            "sha256": response_sha,
            "text": response,
            "origin": {
                "source_complete": materials["response_complete"],
                "selection_start": 0,
                "selection_end": len(response),
                "filename": "作者回复（粘贴文本）",
                "sha256": response_sha,
                "download_url": "",
                "segments": [
                    {
                        "kind": "pasted_text",
                        "number": 1,
                        "start": 0,
                        "end": len(response),
                        "text": response,
                    }
                ],
            },
            "binary_origin": False,
            "download_url": None,
        },
    }
    points = [
        {
            "id": f"P{i + 1:02d}",
            "text": requirement["text"],
            "original_context": requirement["original_context"],
            "label": "编辑预拆要求 · 保留原意见上下文",
            "start": 0,
            "end": len(requirement["text"]),
            "complete": True,
        }
        for i, requirement in enumerate(materials["requirements"])
    ]
    if credential_like(
        "\n".join(
            [f["text"] for f in files.values()]
            + [p["text"] + "\n" + p["original_context"] for p in points]
            + [materials["source_note"]]
        )
    ):
        raise HTTPException(422, "修回材料含疑似密钥，已阻止发送至模型")
    fingerprint = digest(
        {
            "dossier_id": row.id,
            "revision": revision,
            "materials": materials,
            "versions": [old["content_digest"], new["content_digest"]],
            "originals": [
                old["origin"]["sha256"],
                new["origin"]["sha256"],
            ],
        }
    )
    return row, {
        "manuscript_id": row.id,  # Adapter input only; output is explicitly a dossier check.
        "request_id": check_id,
        "revision": revision,
        "base_version_id": base.id,
        "revised_version_id": revised.id,
        "source_fingerprint": fingerprint,
        "rereview_required": False,
        "files": files,
        "points": points,
        "point_count": len(points),
        "all_points_included": materials["requirements_complete"],
    }


def private_report(report, source_data):
    report = deepcopy(report)
    report["schema"] = "dossier-revision-comparison.v1"
    report["dossier_id"] = report.pop("manuscript_id")
    report.pop("rereview_required", None)
    report["requirement_segmentation"] = "human-prepared-v1"
    for row in report["rows"]:
        for citation in row["citations"]:
            item = source_data["files"][citation["kind"]]
            citation["download_url"] = item["download_url"]
            citation["filename"] = item.get("filename") or "作者回复（粘贴文本）"
            if not item["binary_origin"]:
                citation.pop("original", None)
            if citation["kind"] == "response":
                citation["source_type"] = "pasted_text"
    return report


def packet_digest(materials, report):
    return digest({"schema": "dossier-revision-check.v1", "materials": materials, "report": report})


def verified_packet(db, actor, dossier_id, check, *, write=False):
    row = access.load(db, actor, dossier_id, write=write)
    if check.dossier_id != row.id or check.journal_id != row.journal_id:
        raise HTTPException(404, "修回核对不存在或无权访问")
    if packet_digest(check.materials_json, check.report_json) != check.digest:
        raise HTTPException(409, "修回核对快照摘要不一致")
    _, sources = source(
        db, actor, row.id, check.materials_json, check.id, check.revision, current=False
    )
    if check.report_json.get("source_fingerprint") != sources["source_fingerprint"]:
        raise HTTPException(409, "修回核对依赖的材料已变化")
    return row, sources
