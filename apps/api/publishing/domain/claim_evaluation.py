"""Authenticated, read-only export for independent source-based evaluation."""

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..security import Actor, get_actor
from . import dossier_access as access
from .claim_evaluation_package import package_projection
from .evaluation_sources import evaluation_material

router = APIRouter(prefix="/api/dossiers", tags=["independent evidence evaluation"])


@router.get("/{dossier_id}/answers/{answer_id}/evaluation-package")
def evaluation_package(
    dossier_id: UUID,
    answer_id: UUID,
    actor: Actor = Depends(get_actor),
    db: Session = Depends(get_db),
):
    row, item, answer, source, entries, _ = evaluation_material(db, actor, dossier_id, answer_id)
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
