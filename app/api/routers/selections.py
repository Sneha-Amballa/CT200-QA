"""
Selections and QA Router.

Handles QA selection management, cross-version staleness verification,
and the API contract for LLM question-answer generation.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session, get_qa_service
from app.api.schemas import (
    GenerateQARequest,
    GenerateQAResponse,
    SelectionCreateRequest,
    SelectionResponse,
    StalenessResponse,
)
from app.db.models import SavedQASelection
from app.services.qa import QAService

router = APIRouter(prefix="/selections", tags=["Selections & QA"])


@router.post(
    "",
    response_model=SelectionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a QA selection pinned to a manual section",
)
def create_selection(
    req: SelectionCreateRequest,
    db: Session = Depends(get_db_session),
    qa_service: QAService = Depends(get_qa_service),
):
    """
    Creates a new QA selection record:
    - Verifies target section exists in the given manual version.
    - Captures and binds the current section normalized content hash.
    - Sets initial status to 'pending'.
    """
    try:
        selection = qa_service.create_selection(
            version_id=req.version_id,
            section_number=req.section_number,
            session=db,
            metadata=req.metadata,
        )
        return SelectionResponse(**selection.to_dict())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.get(
    "/{selection_id}/staleness",
    response_model=StalenessResponse,
    summary="Check if a saved selection's content hash is current or stale",
)
def check_staleness(
    selection_id: str,
    target_version: Optional[str] = Query(
        None,
        description="Target manual version to check against (defaults to source version)",
    ),
    db: Session = Depends(get_db_session),
    qa_service: QAService = Depends(get_qa_service),
):
    """
    Compares the snapshot source content hash with the target version's section hash:
    - Returns is_stale=False if content is identical.
    - Returns is_stale=True with explanation if content changed or section was removed.
    """
    try:
        report = qa_service.check_staleness(
            selection_id=selection_id,
            session=db,
            target_version_id=target_version,
        )
        return StalenessResponse(**report)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )


@router.post(
    "/{selection_id}/generate-qa",
    response_model=GenerateQAResponse,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    summary="Trigger QA generation for a selection (contract stub)",
)
def generate_qa(
    selection_id: str,
    req: Optional[GenerateQARequest] = None,
    db: Session = Depends(get_db_session),
):
    """
    API contract for triggering LLM QA generation:
    - Validates selection exists.
    - Explicitly reports 501 Not Implemented (scheduled for Step 6) rather than returning fake results.
    """
    sel = db.query(SavedQASelection).filter_by(id=selection_id).first()
    if not sel:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"SavedQASelection '{selection_id}' not found.",
        )

    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            f"LLM QA generation pipeline is not yet implemented (scheduled for Step 6). "
            f"Selection '{selection_id}' for Section {sel.section_number} ({sel.section_title}) "
            f"remains in '{sel.status}' status."
        ),
    )
