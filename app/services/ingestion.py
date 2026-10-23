"""
Manual Ingestion Service.

Handles idempotent ingestion of CT-200 manual versions into the database:
- Reuses the existing extraction and hierarchy construction layers.
- Persists ManualVersion and associated SectionRecord entities.
- Guarantees idempotency: re-running ingestion does not create duplicate
  manual versions or duplicate section rows.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.db.models import ManualVersion, SectionRecord
from app.hierarchy.builder import build_hierarchy
from app.hierarchy.models import DocumentHierarchy
from app.parsing.extract import extract


def compute_file_hash(file_path: str | Path) -> str:
    """Calculates the SHA-256 hash of a file for integrity and idempotency checks."""
    path = Path(file_path)
    sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            sha256.update(chunk)
    return sha256.hexdigest()


class IngestionService:
    """Service for persisting manual versions and section hierarchies."""

    def ingest_manual(
        self,
        pdf_path: str | Path,
        version_id: str,
        session: Session,
        force: bool = False,
        hierarchy: Optional[DocumentHierarchy] = None,
    ) -> ManualVersion:
        """
        Ingests a manual PDF into the database idempotently.

        Args:
            pdf_path: Path to the manual PDF file.
            version_id: Identifier for the version (e.g. 'v1', 'v2').
            session: SQLAlchemy database session.
            force: If True, re-ingests and replaces existing records for this version_id.
            hierarchy: Pre-built DocumentHierarchy if already available.

        Returns:
            The persisted ManualVersion model.
        """
        pdf_path = Path(pdf_path).resolve()
        file_hash = compute_file_hash(pdf_path)

        # Check for existing manual version
        existing = session.query(ManualVersion).filter_by(version_id=version_id).first()
        if existing:
            if not force:
                # Idempotent return without duplicate creation
                return existing
            # If force=True, delete existing version (cascade removes child sections)
            session.delete(existing)
            session.flush()

        # Build hierarchy if not supplied
        if hierarchy is None:
            extract_result = extract(str(pdf_path))
            hierarchy = build_hierarchy(extract_result)

        # Determine page count
        max_page = 0
        for s in hierarchy.all_sections:
            if s.page_references:
                max_page = max(max_page, max(s.page_references))

        manual = ManualVersion(
            version_id=version_id,
            filename=str(pdf_path),
            file_hash=file_hash,
            title=hierarchy.title or "CardioTrack CT-200 Technical & User Manual",
            total_pages=max_page,
            total_sections=len(hierarchy.all_sections),
            source_metadata={
                "anomalies_detected": len(hierarchy.detected_anomalies),
                "anomalies": hierarchy.detected_anomalies,
            },
        )
        session.add(manual)
        session.flush()  # Populates manual.id

        # Insert section records
        for sec in hierarchy.all_sections:
            sec_record = SectionRecord(
                manual_version_id=manual.id,
                version_id=version_id,
                section_number=sec.section_number,
                title=sec.title,
                parent_number=sec.parent_number,
                hierarchy_level=sec.hierarchy_level,
                numbering_depth=sec.numbering_depth,
                order_index=sec.order_index,
                page_references=sec.page_references,
                content_hash=sec.content_hash(),
                normalized_text=sec.get_normalized_text(),
                raw_text=sec.get_raw_text(),
                body_blocks=[b.to_dict() for b in sec.body_blocks],
                tables=[t.to_dict() for t in sec.tables],
                flags=sec.flags,
            )
            session.add(sec_record)

        session.commit()
        session.refresh(manual)
        return manual
