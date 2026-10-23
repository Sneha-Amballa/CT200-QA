"""
Manuals Router.

Handles PDF manual upload/ingestion, version listing, section hierarchy navigation,
individual section retrieval with tables/blocks, and text search.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session, get_ingestion_service
from app.api.schemas import (
    ManualListResponse,
    ManualVersionResponse,
    SearchResponse,
    SearchResultItem,
    SectionDetailResponse,
    SectionListResponse,
    SectionSummaryResponse,
)
from app.db.models import ManualVersion, SectionRecord
from app.services.ingestion import IngestionService

router = APIRouter(prefix="/manuals", tags=["Manuals"])

UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@router.post(
    "/ingest",
    response_model=ManualVersionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a manual PDF",
)
async def ingest_manual(
    file: UploadFile = File(..., description="PDF manual file to ingest"),
    version_id: str = Form(..., description="Unique version identifier (e.g. 'v1', 'v2')"),
    force: bool = Form(False, description="Re-ingest and overwrite existing version records"),
    db: Session = Depends(get_db_session),
    ingestion_service: IngestionService = Depends(get_ingestion_service),
):
    """
    Ingests a manual PDF into the database:
    - Validates PDF file extension.
    - Enforces safe filename saving (prevents path traversal).
    - Reuses extraction and hierarchy building pipeline.
    - Idempotent: returns existing version if already ingested and force is False.
    """
    # 1. Validate version identifier format
    clean_version = version_id.strip()
    if not clean_version or not re.match(r"^[a-zA-Z0-9_\.-]+$", clean_version):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid version_id. Must contain only alphanumeric characters, dots, dashes, and underscores.",
        )

    # 2. Validate file extension and presence
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported file type. Only PDF documents (.pdf) are accepted.",
        )

    # 3. Sanitize filename and prepare secure upload destination
    safe_basename = os.path.basename(file.filename)
    safe_basename = "".join(c for c in safe_basename if c.isalnum() or c in (".", "_", "-"))
    if not safe_basename.lower().endswith(".pdf"):
        safe_basename += ".pdf"

    dest_filename = f"{clean_version}_{safe_basename}"
    dest_path = UPLOAD_DIR / dest_filename

    # Save uploaded file safely
    try:
        content = await file.read()
        if not content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded PDF file is empty (0 bytes).",
            )
        with open(dest_path, "wb") as f:
            f.write(content)
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded PDF to disk.",
        )

    # 4. Ingest via IngestionService
    try:
        manual = ingestion_service.ingest_manual(
            pdf_path=dest_path,
            version_id=clean_version,
            session=db,
            force=force,
        )
        return manual
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion processing failed: {str(e)}",
        )


@router.get(
    "",
    response_model=ManualListResponse,
    summary="List all ingested manual versions",
)
def list_manuals(db: Session = Depends(get_db_session)):
    """Returns a list of all manual versions currently ingested."""
    manuals = db.query(ManualVersion).order_by(ManualVersion.id).all()
    return ManualListResponse(
        manuals=[ManualVersionResponse.model_validate(m) for m in manuals],
        total=len(manuals),
    )


@router.get(
    "/{version_id}/sections",
    response_model=SectionListResponse,
    summary="List sections for a manual version",
)
def list_sections(
    version_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db_session),
):
    """Retrieves paginated section hierarchy nodes for the specified manual version."""
    manual = db.query(ManualVersion).filter_by(version_id=version_id).first()
    if not manual:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manual version '{version_id}' not found.",
        )

    query = (
        db.query(SectionRecord)
        .filter_by(version_id=version_id)
        .order_by(SectionRecord.order_index)
    )
    total = query.count()
    sections = query.offset(skip).limit(limit).all()

    return SectionListResponse(
        version_id=version_id,
        total_sections=total,
        sections=[SectionSummaryResponse.model_validate(s) for s in sections],
    )


@router.get(
    "/{version_id}/sections/{section_number}",
    response_model=SectionDetailResponse,
    summary="Retrieve detailed section content and tables",
)
def get_section(
    version_id: str,
    section_number: str,
    db: Session = Depends(get_db_session),
):
    """Retrieves full content, body blocks, and tables for an individual section."""
    manual = db.query(ManualVersion).filter_by(version_id=version_id).first()
    if not manual:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manual version '{version_id}' not found.",
        )

    sec = (
        db.query(SectionRecord)
        .filter_by(version_id=version_id, section_number=section_number)
        .first()
    )
    if not sec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Section '{section_number}' not found in manual version '{version_id}'.",
        )

    return SectionDetailResponse.model_validate(sec)


@router.get(
    "/{version_id}/search",
    response_model=SearchResponse,
    summary="Search manual section titles and content",
)
def search_sections(
    version_id: str,
    q: str = Query(..., min_length=1, description="Search query string"),
    db: Session = Depends(get_db_session),
):
    """Searches section titles and body prose for occurrences of query term."""
    manual = db.query(ManualVersion).filter_by(version_id=version_id).first()
    if not manual:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Manual version '{version_id}' not found.",
        )

    query_term = q.strip()
    if not query_term:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Search query cannot be empty.",
        )

    # Filter section records matching title or normalized text
    matched_sections = (
        db.query(SectionRecord)
        .filter(
            SectionRecord.version_id == version_id,
            or_(
                SectionRecord.title.ilike(f"%{query_term}%"),
                SectionRecord.normalized_text.ilike(f"%{query_term}%"),
            ),
        )
        .order_by(SectionRecord.order_index)
        .all()
    )

    results: List[SearchResultItem] = []
    lower_query = query_term.lower()

    for sec in matched_sections:
        title_matched = lower_query in sec.title.lower()
        matched_in = "title" if title_matched else "body"

        # Generate contextual snippet
        text = sec.normalized_text
        idx = text.lower().find(lower_query)
        if idx != -1:
            start = max(0, idx - 40)
            end = min(len(text), idx + len(query_term) + 60)
            snippet = ("..." if start > 0 else "") + text[start:end].strip() + ("..." if end < len(text) else "")
        else:
            snippet = sec.title

        results.append(
            SearchResultItem(
                section_number=sec.section_number,
                title=sec.title,
                page_references=sec.page_references,
                content_hash=sec.content_hash,
                matched_in=matched_in,
                snippet=snippet,
            )
        )

    return SearchResponse(
        version_id=version_id,
        query=query_term,
        total_results=len(results),
        results=results,
    )
