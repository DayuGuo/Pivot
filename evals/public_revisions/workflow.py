"""Development-only, actual API workflow over licensed public reference files.

All workflow identities, checks and decisions are synthetic test actors. Original
published reviewer paragraphs are reference text, never impersonated signatures.
No application/model functions are mocked. Only test fixture inputs are changed.
"""

import base64
import json
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from tests.api import test_publishing_decisions as decisions
from tests.api import test_publishing_peer_review as peer
from tests.api import test_publishing_screening as screening
from tests.api.test_publishing_intake import complete_data, detail

ROOT = Path(__file__).resolve().parents[2]


def cases():
    return json.loads((ROOT / "evals/public_revisions/manifest.json").read_text())["cases"]


def import_file(client, mid, info, *, purpose="manuscript", first=1, last=None, excerpt=False):
    current = detail(client, mid)
    path = ROOT / info["path"]
    prepared = client.post(
        f"/api/publishing/manuscripts/{mid}/document-imports",
        json={
            "request_id": str(uuid4()),
            "expected_revision": current["revision"],
            "version_id": current["version"]["id"],
            "filename": path.name,
            "purpose": purpose,
            "content_base64": base64.b64encode(path.read_bytes()).decode(),
            "authorized_material": True,
            "material_scope": "excerpt" if excerpt else "complete",
            "source_kind": "public_authorized",
            "source_note": "公开许可回归参考资料，工作流和责任人均为合成测试。来源、作者和变换记录见 evals/public_revisions/manifest.json；CC BY 4.0。",
        },
    )
    assert prepared.status_code == 200, prepared.text
    iid = prepared.json()["import_id"]
    imported = client.get(f"/api/publishing/manuscripts/{mid}/document-imports/{iid}").json()
    # Preparation must not change the formal version or its revision.
    assert detail(client, mid) == current
    confirmed = client.post(
        f"/api/publishing/manuscripts/{mid}/document-imports/{iid}/confirmations",
        json={
            "request_id": str(uuid4()),
            "expected_revision": current["revision"],
            "digest": imported["digest"],
            "first_segment": first,
            "last_segment": last or len(imported["segments"]),
            "acknowledged_original": True,
            "acknowledged_text": True,
            "acknowledged_scope": True,
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    return confirmed.json()


def build_case(client, login, world, case, base_format, revised_format, *, unchanged=False):
    """Create a true formal revision chain, with explicitly confirmed API gates."""
    fill = screening.fill
    report_values = peer.report_values
    choice = decisions.choice

    def public_fill(client, created):
        current = fill(client, created)
        version = case["versions"]["1"]
        import_file(
            client,
            current["id"],
            version[base_format],
            first=version["body_first_page"] if base_format == "pdf" else 1,
        )
        return detail(client, current["id"])

    def public_report():
        values = report_values()
        values["author_text"] = "\n\n".join(r["text"] for r in case["review_requirements"])
        values["answers_json"]["rigor"] = (
            "公开许可参考段落用于软件回归，不代表本系统对论文的科学评价。"
        )
        return values

    def sandbox_choice(*args, **kwargs):
        values = choice(*args, **kwargs)
        values["author_letter"] = (
            "这是软件沙盒的合成修回请求，请按已分享的公开许可参考意见核对，不代表原期刊决定。"
        )
        values["author_instructions"] = (
            "请逐项核对已分享的参考意见与本次公开版本、修订说明；本流程仅用于软件回归。"
        )
        return values

    with (
        patch.object(screening, "fill", public_fill),
        patch.object(peer, "report_values", public_report),
        patch.object(decisions, "choice", sandbox_choice),
    ):
        mid = decisions.closed_round(client, login, world)
        rid = detail(client, mid)["review"]["reports"][0]["id"]
        decisions.recommend(client, login, mid)
        decisions.decide(client, login, mid, reports=[rid])
    login("author")
    current = detail(client, mid)
    saved = client.patch(
        f"/api/publishing/manuscripts/{mid}/intake",
        json={
            "request_id": str(uuid4()),
            "expected_revision": current["revision"],
            "data": complete_data(),
        },
    )
    assert saved.status_code == 200, saved.text
    version = case["versions"]["1" if unchanged else "2"]
    import_file(
        client,
        mid,
        version[revised_format],
        first=version["body_first_page"] if revised_format == "pdf" else 1,
    )
    import_file(client, mid, case["response"], purpose="response", excerpt=True)
    before, proposal = peer.propose(client, mid, "submit_revision", {})
    screening.confirm(client, before, proposal)
    assert detail(client, mid)["stage"] == "revision_assessment"
    login("editor")
    return mid
