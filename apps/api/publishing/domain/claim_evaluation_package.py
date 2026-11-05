"""Pure, allowlisted evaluation projection; never export model or human labels."""

from copy import deepcopy
from secrets import SystemRandom
from uuid import uuid4

from .dossier_evidence import leaf_fields, source_label


class InvalidEvaluationSource(ValueError):
    pass


def citation_projection(citation, *, version, text, file_sha256):
    """Check archived Unicode coordinates against the actual frozen version."""
    if not isinstance(citation, dict) or any(
        citation.get(key) != version[key] for key in ("version_id", "version_no", "content_digest")
    ):
        raise InvalidEvaluationSource("citation_version")
    kind = citation.get("kind")
    field = citation.get("field_path")
    if kind == "text":
        value = text
        if field is not None or citation.get("file_sha256") != file_sha256:
            raise InvalidEvaluationSource("citation_file")
    elif kind == "metadata" and isinstance(field, str):
        value = dict(leaf_fields(version["data"])).get(field)
    else:
        raise InvalidEvaluationSource("citation_kind")
    start, end, quote = (citation.get(k) for k in ("start", "end", "quote"))
    if (
        not isinstance(value, str)
        or type(start) is not int
        or type(end) is not int
        or start < 0
        or end <= start
        or end > len(value)
        or not isinstance(quote, str)
        or not quote.strip()
        or value[start:end] != quote
    ):
        raise InvalidEvaluationSource("citation_span")
    return {
        "kind": kind,
        "field_path": field,
        "label": source_label(field),
        "quote": quote,
        "start": start,
        "end": end,
        "line_start": value.count("\n", 0, start) + 1 if kind == "text" else None,
        "line_end": value.count("\n", 0, end - 1) + 1 if kind == "text" else None,
    }


def package_projection(source, claims, *, claim_ids=None):
    """Random identifiers/order do not reveal adopted/withheld groups or indexes."""
    entries = [
        {
            "id": claim_ids[index] if claim_ids is not None else str(uuid4()),
            "text": c["text"],
            "citations": deepcopy(c["citations"]),
            "assessment": {"verdict": None, "note": ""},
        }
        for index, c in enumerate(claims)
    ]
    SystemRandom().shuffle(entries)
    return {
        "schema": "claim-evaluation-package.v1",
        "package_id": str(uuid4()),
        "evaluation_mode": "ai_labels_hidden",
        "instructions": [
            "本包含完整版本资料和作者信息，仅可用于获授权的内部核对。",
            "已隐藏AI判定和既有人工意见并打乱结论顺序；结论文案和材料仍可能影响判断，不等于双盲评审。",
            "请先独立阅读原文，再逐条填写supported、unsupported或uncertain及具体理由；尚未完成的评价保持null。",
            "offset为Unicode码点，start包含、end不包含；metadata相对field_path字段，text相对source.text。",
            "下载文件的评价暂不支持回传；不会写入系统反馈、确认稿件、发送邮件或作出出版决定。",
            "原文逐字定位不代表科学正确；ORCID和作者信息未因此获得身份认证。",
        ],
        "source": deepcopy(source),
        "claims": entries,
        "human_feedback_is_not_publication_approval": True,
    }
