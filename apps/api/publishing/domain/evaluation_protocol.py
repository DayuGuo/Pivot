"""Untrusted returned files change assessments only; deterministic disagreement counts."""

import hashlib
import json
from copy import deepcopy


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


class InvalidReturn(ValueError):
    pass


def assessments(template, returned):
    if (
        not isinstance(returned, dict)
        or len(json.dumps(returned, ensure_ascii=False).encode()) > 2097152
    ):
        raise InvalidReturn("评价文件过大或格式错误")
    claims = returned.get("claims")
    original = template["claims"]
    if not isinstance(claims, list) or len(claims) != len(original):
        raise InvalidReturn("结论缺失或增加，请使用已登记评价包，仅填写assessment")
    clean = deepcopy(returned)
    by_id = {c["id"]: c for c in original}
    result = {}
    for claim in clean["claims"]:
        if (
            not isinstance(claim, dict)
            or not isinstance(claim.get("id"), str)
            or claim["id"] not in by_id
            or claim["id"] in result
        ):
            raise InvalidReturn("结论ID重复或不属于本评价包")
        assessment = claim.get("assessment")
        if not isinstance(assessment, dict) or set(assessment) != {"verdict", "note"}:
            raise InvalidReturn("每条评价只允许verdict和note")
        verdict, note = assessment["verdict"], assessment["note"]
        if not isinstance(note, str) or "\x00" in note or len(note) > 2000:
            raise InvalidReturn("评价理由须为不含空字符的文字，最多2000字")
        if verdict is None:
            if note != "":
                raise InvalidReturn("未评价项目请保留null及空理由")
        elif (
            not isinstance(verdict, str)
            or verdict not in {"supported", "unsupported", "uncertain"}
            or len(note.strip()) < 5
        ):
            raise InvalidReturn("评价请选择supported/unsupported/uncertain并填写至少5字理由")
        result[claim["id"]] = {"verdict": verdict, "note": note.strip()}
        claim["assessment"] = deepcopy(by_id[claim["id"]]["assessment"])
    # Reordering is permitted; every other byte-equivalent JSON value remains frozen.
    clean["claims"].sort(key=lambda c: c["id"])
    expected = deepcopy(template)
    expected["claims"].sort(key=lambda c: c["id"])
    if digest(clean) != digest(expected):
        raise InvalidReturn("原文、作者、版本、结论或引文已修改，不能回传；仅允许填写assessment")
    if not any(a["verdict"] is not None for a in result.values()):
        raise InvalidReturn("至少填写一条实际评价后才能回传")
    return result


def return_digest(package, values):
    return digest(
        {
            "schema": "evaluation-return.v1",
            "package_id": package.id,
            "packet_digest": package.packet_digest,
            "assessments": values,
        }
    )


def disagreement(packages, latest):
    """Latest confirmed return per assigned code; no majority publication decision."""
    targets = {}
    for package in packages:
        result = latest.get(package.id)
        for opaque, target in package.claim_map.items():
            key = (target["bucket"], target["index"])
            row = targets.setdefault(
                key,
                {
                    "claim_bucket": key[0],
                    "claim_index": key[1],
                    "text": target["claim"]["text"],
                    "supported": 0,
                    "unsupported": 0,
                    "uncertain": 0,
                    "unanswered": 0,
                    "opinions": [],
                },
            )
            opinion = result.assessments_json[opaque] if result else {"verdict": None, "note": ""}
            row[opinion["verdict"] or "unanswered"] += 1
            row["opinions"].append(
                {
                    "evaluator_code": package.evaluator_code,
                    **opinion,
                    "return_id": result.id if result else None,
                }
            )
    for row in targets.values():
        row["disagreement"] = row["supported"] > 0 and row["unsupported"] > 0
    return {
        "registered_slots": len(packages),
        "confirmed_slots": len(latest),
        "disputed_claims": sum(r["disagreement"] for r in targets.values()),
        "claims": [targets[k] for k in sorted(targets)],
        "scope": "latest owner-confirmed return per declared evaluator code; identities not authenticated; no majority decision",
    }
