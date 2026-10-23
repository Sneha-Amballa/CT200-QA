"""
SQLAlchemy Persistent Data Models.

Defines schemas and relationships for:
1. ManualVersion - manual metadata, ingested timestamp, and source details.
2. SectionRecord - hierarchy sections, order index, page refs, and content hashes.
3. VersionComparisonRecord & SectionDiffRecord - structural diff results and summaries.
4. SavedQASelection - QA generation selection tracking, content hashes, and status.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class ManualVersion(Base):
    """Represents an ingested version of a device manual (e.g. v1, v2)."""

    __tablename__ = "manual_versions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version_id = Column(String(50), unique=True, nullable=False, index=True)
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    total_pages = Column(Integer, nullable=False, default=0)
    total_sections = Column(Integer, nullable=False, default=0)
    ingested_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    source_metadata = Column(JSON, nullable=False, default=dict)

    # Relationships
    sections = relationship(
        "SectionRecord",
        back_populates="manual_version",
        cascade="all, delete-orphan",
        order_by="SectionRecord.order_index",
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "version_id": self.version_id,
            "filename": self.filename,
            "file_hash": self.file_hash,
            "title": self.title,
            "total_pages": self.total_pages,
            "total_sections": self.total_sections,
            "ingested_at": self.ingested_at.isoformat() if self.ingested_at else None,
            "source_metadata": self.source_metadata,
        }


class SectionRecord(Base):
    """Represents a section node within an ingested manual version."""

    __tablename__ = "section_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_version_id = Column(
        Integer,
        ForeignKey("manual_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_id = Column(String(50), nullable=False, index=True)
    section_number = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    parent_number = Column(String(50), nullable=True)
    hierarchy_level = Column(Integer, nullable=False)
    numbering_depth = Column(Integer, nullable=False)
    order_index = Column(Integer, nullable=False)
    page_references = Column(JSON, nullable=False, default=list)
    content_hash = Column(String(64), nullable=False, index=True)
    normalized_text = Column(Text, nullable=False)
    raw_text = Column(Text, nullable=False)
    body_blocks = Column(JSON, nullable=False, default=list)
    tables = Column(JSON, nullable=False, default=list)
    flags = Column(JSON, nullable=False, default=list)

    # Relationship
    manual_version = relationship("ManualVersion", back_populates="sections")

    __table_args__ = (
        UniqueConstraint(
            "manual_version_id",
            "section_number",
            name="uq_manual_version_section_number",
        ),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "manual_version_id": self.manual_version_id,
            "version_id": self.version_id,
            "section_number": self.section_number,
            "title": self.title,
            "parent_number": self.parent_number,
            "hierarchy_level": self.hierarchy_level,
            "numbering_depth": self.numbering_depth,
            "order_index": self.order_index,
            "page_references": self.page_references,
            "content_hash": self.content_hash,
            "normalized_text": self.normalized_text,
            "flags": self.flags,
            "table_count": len(self.tables) if self.tables else 0,
            "body_block_count": len(self.body_blocks) if self.body_blocks else 0,
        }


class VersionComparisonRecord(Base):
    """Represents a persisted comparison between two manual versions."""

    __tablename__ = "version_comparisons"

    id = Column(Integer, primary_key=True, autoincrement=True)
    v1_version_id = Column(String(50), nullable=False, index=True)
    v2_version_id = Column(String(50), nullable=False, index=True)
    compared_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    summary = Column(JSON, nullable=False, default=dict)

    # Relationships
    section_diffs = relationship(
        "SectionDiffRecord",
        back_populates="comparison",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "v1_version_id",
            "v2_version_id",
            name="uq_version_comparison_pair",
        ),
    )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "v1_version_id": self.v1_version_id,
            "v2_version_id": self.v2_version_id,
            "compared_at": self.compared_at.isoformat() if self.compared_at else None,
            "summary": self.summary,
            "diff_count": len(self.section_diffs) if self.section_diffs else 0,
        }


class SectionDiffRecord(Base):
    """Represents the diff of an individual section in a version comparison."""

    __tablename__ = "section_diff_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    comparison_id = Column(
        Integer,
        ForeignKey("version_comparisons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_number = Column(String(50), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False)  # "added", "removed", "modified", "unchanged"
    content_changed = Column(Boolean, nullable=False, default=False)
    page_changed = Column(Boolean, nullable=False, default=False)
    v1_pages = Column(JSON, nullable=False, default=list)
    v2_pages = Column(JSON, nullable=False, default=list)
    v1_content_hash = Column(String(64), nullable=True)
    v2_content_hash = Column(String(64), nullable=True)
    word_diff = Column(Text, nullable=True)
    table_diff = Column(JSON, nullable=True)
    explanation = Column(Text, nullable=False, default="")

    # Relationship
    comparison = relationship("VersionComparisonRecord", back_populates="section_diffs")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "comparison_id": self.comparison_id,
            "section_number": self.section_number,
            "title": self.title,
            "status": self.status,
            "content_changed": self.content_changed,
            "page_changed": self.page_changed,
            "v1_pages": self.v1_pages,
            "v2_pages": self.v2_pages,
            "v1_content_hash": self.v1_content_hash,
            "v2_content_hash": self.v2_content_hash,
            "word_diff": self.word_diff,
            "table_diff": self.table_diff,
            "explanation": self.explanation,
        }


class SavedQASelection(Base):
    """
    Represents a user QA selection for a manual section.
    Tracks the source content hash to enable future staleness detection.
    """

    __tablename__ = "saved_qa_selections"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    version_id = Column(String(50), nullable=False, index=True)
    section_number = Column(String(50), nullable=False, index=True)
    section_title = Column(String(255), nullable=False)
    source_content_hash = Column(String(64), nullable=False, index=True)
    qa_result_id = Column(String(100), nullable=True, index=True)
    status = Column(String(50), nullable=False, default="active")  # "pending", "active", "stale", "archived"
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.datetime.now(datetime.timezone.utc),
        onupdate=lambda: datetime.datetime.now(datetime.timezone.utc),
        nullable=False,
    )
    metadata_json = Column(JSON, nullable=False, default=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "version_id": self.version_id,
            "section_number": self.section_number,
            "section_title": self.section_title,
            "source_content_hash": self.source_content_hash,
            "qa_result_id": self.qa_result_id,
            "status": self.status,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata": self.metadata_json,
        }
