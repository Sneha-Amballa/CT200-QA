"""
Comparison Persistence Service.

Persists the results of DocumentComparator to the database, capturing
structural version diffs, table diffs, and substantive changes.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from app.comparison.diff import compare_hierarchies
from app.comparison.models import DocumentComparisonResult
from app.db.models import SectionDiffRecord, VersionComparisonRecord
from app.hierarchy.models import DocumentHierarchy


class ComparisonService:
    """Service for running and persisting document version comparisons."""

    def compare_and_persist(
        self,
        v1_version_id: str,
        v2_version_id: str,
        hier_v1: DocumentHierarchy,
        hier_v2: DocumentHierarchy,
        session: Session,
        force: bool = False,
    ) -> VersionComparisonRecord:
        """
        Runs comparison using existing DocumentComparator and persists results.

        Args:
            v1_version_id: Identifier for base version (e.g. 'v1').
            v2_version_id: Identifier for target version (e.g. 'v2').
            hier_v1: DocumentHierarchy for v1.
            hier_v2: DocumentHierarchy for v2.
            session: SQLAlchemy database session.
            force: If True, re-runs comparison and overwrites existing record.

        Returns:
            The persisted VersionComparisonRecord.
        """
        existing = (
            session.query(VersionComparisonRecord)
            .filter_by(v1_version_id=v1_version_id, v2_version_id=v2_version_id)
            .first()
        )
        if existing:
            if not force:
                return existing
            session.delete(existing)
            session.flush()

        # Run comparison using the domain comparator
        diff_result: DocumentComparisonResult = compare_hierarchies(hier_v1, hier_v2)

        comparison_rec = VersionComparisonRecord(
            v1_version_id=v1_version_id,
            v2_version_id=v2_version_id,
            summary=diff_result.summary.to_dict(),
        )
        session.add(comparison_rec)
        session.flush()  # Populates comparison_rec.id

        for s_diff in diff_result.section_diffs:
            diff_row = SectionDiffRecord(
                comparison_id=comparison_rec.id,
                section_number=s_diff.section_number,
                title=s_diff.title,
                status=s_diff.status,
                content_changed=s_diff.content_changed,
                page_changed=s_diff.page_changed,
                v1_pages=s_diff.v1_pages,
                v2_pages=s_diff.v2_pages,
                v1_content_hash=s_diff.v1_content_hash,
                v2_content_hash=s_diff.v2_content_hash,
                word_diff=s_diff.word_diff,
                table_diff=s_diff.table_diff.to_dict() if s_diff.table_diff else None,
                explanation=s_diff.explanation,
            )
            session.add(diff_row)

        session.commit()
        session.refresh(comparison_rec)
        return comparison_rec
