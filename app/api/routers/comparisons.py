"""
Comparisons Router.

Handles running and retrieving structural document version comparisons.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_comparison_service, get_db_session
from app.api.schemas import ComparisonRequest, ComparisonResponse, SectionDiffResponse
from app.db.models import ManualVersion, SectionDiffRecord, VersionComparisonRecord
from app.services.comparison import ComparisonService

router = APIRouter(prefix="/comparisons", tags=["Comparisons"])


@router.post(
    "",
    response_model=ComparisonResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Compare two manual versions and persist diff results",
)
def create_comparison(
    req: ComparisonRequest,
    db: Session = Depends(get_db_session),
    comparison_service: ComparisonService = Depends(get_comparison_service),
):
    """
    Executes a structural cross-version comparison using DocumentComparator:
    - Verifies both versions exist.
    - Idempotent: returns existing comparison if already computed and force is False.
    - Persists section diffs, table diffs, and substantive change logs.
    """
    m1 = db.query(ManualVersion).filter_by(version_id=req.v1_version_id).first()
    if not m1:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Base manual version '{req.v1_version_id}' not found in database.",
        )

    m2 = db.query(ManualVersion).filter_by(version_id=req.v2_version_id).first()
    if not m2:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Target manual version '{req.v2_version_id}' not found in database.",
        )

    try:
        comparison_rec = comparison_service.compare_and_persist(
            v1_version_id=req.v1_version_id,
            v2_version_id=req.v2_version_id,
            session=db,
            force=req.force,
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Comparison execution failed: {str(e)}",
        )

    diffs = (
        db.query(SectionDiffRecord)
        .filter_by(comparison_id=comparison_rec.id)
        .order_by(SectionDiffRecord.id)
        .all()
    )

    substantive = comparison_rec.summary.get("substantive_changes", []) if comparison_rec.summary else []

    return ComparisonResponse(
        id=comparison_rec.id,
        v1_version_id=comparison_rec.v1_version_id,
        v2_version_id=comparison_rec.v2_version_id,
        compared_at=comparison_rec.compared_at.isoformat() if comparison_rec.compared_at else None,
        summary=comparison_rec.summary,
        substantive_changes=substantive,
        section_diffs=[SectionDiffResponse.model_validate(d) for d in diffs],
    )


@router.get(
    "/{comparison_id}",
    response_model=ComparisonResponse,
    summary="Retrieve a persisted version comparison",
)
def get_comparison(
    comparison_id: str,
    db: Session = Depends(get_db_session),
):
    """
    Retrieves a persisted comparison by its integer ID or pair key (e.g. 'v1_v2').
    """
    rec: Optional[VersionComparisonRecord] = None
    if comparison_id.isdigit():
        rec = db.query(VersionComparisonRecord).filter_by(id=int(comparison_id)).first()
    elif "_" in comparison_id:
        parts = comparison_id.split("_", 1)
        rec = (
            db.query(VersionComparisonRecord)
            .filter_by(v1_version_id=parts[0], v2_version_id=parts[1])
            .first()
        )

    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Comparison '{comparison_id}' not found.",
        )

    diffs = (
        db.query(SectionDiffRecord)
        .filter_by(comparison_id=rec.id)
        .order_by(SectionDiffRecord.id)
        .all()
    )

    substantive = rec.summary.get("substantive_changes", []) if rec.summary else []

    return ComparisonResponse(
        id=rec.id,
        v1_version_id=rec.v1_version_id,
        v2_version_id=rec.v2_version_id,
        compared_at=rec.compared_at.isoformat() if rec.compared_at else None,
        summary=rec.summary,
        substantive_changes=substantive,
        section_diffs=[SectionDiffResponse.model_validate(d) for d in diffs],
    )
