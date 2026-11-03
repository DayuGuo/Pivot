"""Critical human choices reject coercion, missing context and accidental defaults."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from apps.api.publishing.domain.decision_schemas import Assessment, Decision, Recommendation


@pytest.mark.parametrize("invalid", [1, "true", False, None, [], {}])
@pytest.mark.parametrize("field", ["reviewed_current_version", "reviewed_response"])
def test_revision_manual_declarations_are_literal_booleans(invalid, field):
    data = {"reviewed_current_version": True, "reviewed_response": True}
    data[field] = invalid
    with pytest.raises(ValidationError):
        Assessment.model_validate(
            {
                "outcome": "ready_for_chief",
                "notes": "负责人必须独立阅读当前版本与回复，不能从模型或整数取得声明。",
                "declarations": data,
            }
        )


def test_sharing_four_actual_reports_is_not_confused_with_round_target_three():
    data = {
        "decision_code": "accept",
        "rationale_private": "主编独立核对实际报告和当前版本，作出明确的本地合成测试决定。",
        "author_letter": "本刊已经完成全部规定的人类审核，现将此决定及反馈告知作者。",
        "share_report_ids": [str(uuid4()) for _ in range(4)],
        "share_reports_anonymity_reviewed": True,
    }
    assert len(Decision.model_validate(data).share_report_ids) == 4
    data["share_reports_anonymity_reviewed"] = False
    with pytest.raises(ValidationError):
        Decision.model_validate(data)
    data["share_reports_anonymity_reviewed"] = True
    duplicate = str(uuid4())
    data["share_report_ids"] = [duplicate, duplicate.upper()]
    with pytest.raises(ValidationError):
        Decision.model_validate(data)


@pytest.mark.parametrize(
    "code,kind", [("request_revision", None), ("accept", "minor"), ("reject", "major")]
)
def test_recommendation_revision_kind_is_conditional(code, kind):
    with pytest.raises(ValidationError):
        Recommendation.model_validate(
            {
                "recommendation": code,
                "revision_kind": kind,
                "rationale_private": "编辑根据本轮材料与报告记录人工建议，不能代替主编决定。",
                "author_letter": "请作者依据具体的决定类型与修回要求处理，所有操作需本人确认。",
            }
        )


def test_rereview_requires_explicit_anonymous_material_check():
    with pytest.raises(ValidationError):
        Assessment.model_validate(
            {
                "outcome": "rereview",
                "notes": "重新送审前必须确认当前版本匿名材料已经由负责人本人检查。",
                "declarations": {"reviewed_current_version": True, "reviewed_response": True},
            }
        )
