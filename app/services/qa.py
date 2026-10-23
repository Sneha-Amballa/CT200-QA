"""
QA Selection and Staleness Management Service.

Coordinates between relational SavedQASelection metadata and document-backed
JSON QA storage, maintaining content hashes for automated staleness detection.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.db.models import SavedQASelection, SectionRecord
from app.db.qa_store import BaseQADocumentStore, JSONFileQAStore


class QAService:
    """Service for managing QA selections, document output persistence, and staleness."""

    def __init__(self, qa_store: Optional[BaseQADocumentStore] = None):
        self.qa_store = qa_store or JSONFileQAStore()

    def create_selection(
        self,
        version_id: str,
        section_number: str,
        session: Session,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SavedQASelection:
        """
        Creates a new QA selection record, binding the current section content hash.

        Args:
            version_id: Manual version (e.g. 'v1').
            section_number: Section number (e.g. '4.2').
            session: SQLAlchemy session.
            metadata: Optional additional metadata dict.

        Returns:
            The created SavedQASelection.
        """
        sec = (
            session.query(SectionRecord)
            .filter_by(version_id=version_id, section_number=section_number)
            .first()
        )
        if not sec:
            raise ValueError(f"Section '{section_number}' not found in manual version '{version_id}'.")

        selection = SavedQASelection(
            version_id=version_id,
            section_number=section_number,
            section_title=sec.title,
            source_content_hash=sec.content_hash,
            qa_result_id=None,
            status="pending",
            metadata_json=metadata or {},
        )
        session.add(selection)
        session.commit()
        session.refresh(selection)
        return selection

    def save_qa_result(
        self,
        selection_id: str,
        qa_document: Dict[str, Any],
        session: Session,
    ) -> Tuple[SavedQASelection, str]:
        """
        Persists generated QA document in QA store and updates selection reference.

        Args:
            selection_id: ID of the SavedQASelection.
            qa_document: Structured QA document payload.
            session: SQLAlchemy session.

        Returns:
            Tuple of (updated SavedQASelection, qa_doc_id).
        """
        selection = session.query(SavedQASelection).filter_by(id=selection_id).first()
        if not selection:
            raise ValueError(f"SavedQASelection '{selection_id}' not found.")

        # Ensure required metadata exists in QA document
        qa_document["version_id"] = selection.version_id
        qa_document["section_number"] = selection.section_number
        qa_document["section_title"] = selection.section_title
        qa_document["source_content_hash"] = selection.source_content_hash
        qa_document["saved_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        doc_id = self.qa_store.save(qa_document)

        selection.qa_result_id = doc_id
        selection.status = "active"
        session.commit()
        session.refresh(selection)
        return selection, doc_id

    def check_staleness(
        self,
        selection_id: str,
        session: Session,
        target_version_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compares selection's source content hash against the target version's section hash.

        Args:
            selection_id: ID of the SavedQASelection.
            session: SQLAlchemy session.
            target_version_id: Optional target version (e.g. check v1 QA against v2).
                               Defaults to the selection's own version.

        Returns:
            Staleness report dict.
        """
        selection = session.query(SavedQASelection).filter_by(id=selection_id).first()
        if not selection:
            raise ValueError(f"SavedQASelection '{selection_id}' not found.")

        check_version = target_version_id or selection.version_id
        target_sec = (
            session.query(SectionRecord)
            .filter_by(version_id=check_version, section_number=selection.section_number)
            .first()
        )

        if not target_sec:
            is_stale = True
            reason = (
                f"Section {selection.section_number} was not found in version '{check_version}' "
                "(may have been removed or renumbered)."
            )
            curr_hash = None
        else:
            curr_hash = target_sec.content_hash
            if curr_hash == selection.source_content_hash:
                is_stale = False
                reason = "Content hash matches source hash; QA content is up to date."
            else:
                is_stale = True
                reason = (
                    f"Content changed between source ({selection.source_content_hash[:8]}) "
                    f"and version '{check_version}' ({curr_hash[:8]})."
                )

        return {
            "selection_id": selection.id,
            "source_version_id": selection.version_id,
            "target_version_id": check_version,
            "section_number": selection.section_number,
            "section_title": selection.section_title,
            "source_content_hash": selection.source_content_hash,
            "current_content_hash": curr_hash,
            "is_stale": is_stale,
            "reason": reason,
        }
