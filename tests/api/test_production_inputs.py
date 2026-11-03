"""Proofreading cannot claim human checks through truthy numeric/string inputs."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from apps.api.publishing.domain.production_schemas import ConfirmProof, PreparePreview, SendProof


@pytest.mark.parametrize("invalid", [1, "true", False, None])
@pytest.mark.parametrize("field", ["proof_reviewed", "metadata_reviewed"])
def test_send_proof_requires_explicit_human_boolean(field, invalid):
    declarations = {"proof_reviewed": True, "metadata_reviewed": True}
    declarations[field] = invalid
    with pytest.raises(ValidationError):
        SendProof.model_validate({"declarations": declarations})


@pytest.mark.parametrize("invalid", [1, "true", False, None])
def test_author_proof_response_cannot_coerce_review_declaration(invalid):
    with pytest.raises(ValidationError):
        ConfirmProof.model_validate(
            {
                "package_id": str(uuid4()),
                "outcome": "approve",
                "notes": "",
                "declarations": {"proof_reviewed": invalid},
            }
        )


@pytest.mark.parametrize("invalid", [1, "true", False, None])
@pytest.mark.parametrize("field", ["metadata_reviewed", "approved_proof_reviewed"])
def test_preview_requires_explicit_human_boolean(field, invalid):
    declarations = {"metadata_reviewed": True, "approved_proof_reviewed": True}
    declarations[field] = invalid
    with pytest.raises(ValidationError):
        PreparePreview.model_validate({"declarations": declarations})
