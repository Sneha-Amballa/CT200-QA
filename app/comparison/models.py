"""
Document Version Comparison Data Models.

Defines structural representation of section-level and table-level
version differences, distinguishing content modifications from page reflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class TableRowDiff:
    row_key: str
    change_type: str  # "added", "removed", "modified", "unchanged"
    v1_cells: Optional[List[str]] = None
    v2_cells: Optional[List[str]] = None
    cell_diffs: Dict[int, Tuple[str, str]] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_key": self.row_key,
            "change_type": self.change_type,
            "v1_cells": self.v1_cells,
            "v2_cells": self.v2_cells,
            "cell_diffs": self.cell_diffs,
            "description": self.description,
        }


@dataclass
class TableDiff:
    table_id: str
    section_number: str
    has_changes: bool
    row_diffs: List[TableRowDiff] = field(default_factory=list)
    added_rows: List[TableRowDiff] = field(default_factory=list)
    removed_rows: List[TableRowDiff] = field(default_factory=list)
    modified_rows: List[TableRowDiff] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_id": self.table_id,
            "section_number": self.section_number,
            "has_changes": self.has_changes,
            "added_count": len(self.added_rows),
            "removed_count": len(self.removed_rows),
            "modified_count": len(self.modified_rows),
            "modified_rows": [r.to_dict() for r in self.modified_rows],
            "added_rows": [r.to_dict() for r in self.added_rows],
        }


@dataclass
class SectionDiff:
    section_number: str
    title: str
    status: str                         # "added", "removed", "modified", "unchanged"
    content_changed: bool
    page_changed: bool
    v1_pages: List[int]
    v2_pages: List[int]
    v1_content_hash: Optional[str] = None
    v2_content_hash: Optional[str] = None
    v1_normalized_text: Optional[str] = None
    v2_normalized_text: Optional[str] = None
    v1_raw_text: Optional[str] = None
    v2_raw_text: Optional[str] = None
    word_diff: Optional[str] = None
    table_diff: Optional[TableDiff] = None
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "section_number": self.section_number,
            "title": self.title,
            "status": self.status,
            "content_changed": self.content_changed,
            "page_changed": self.page_changed,
            "v1_pages": self.v1_pages,
            "v2_pages": self.v2_pages,
            "v1_content_hash": self.v1_content_hash,
            "v2_content_hash": self.v2_content_hash,
            "explanation": self.explanation,
            "table_diff": self.table_diff.to_dict() if self.table_diff else None,
            "word_diff": self.word_diff,
        }


@dataclass
class ComparisonSummary:
    total_sections_v1: int
    total_sections_v2: int
    added_count: int
    removed_count: int
    modified_count: int
    unchanged_count: int
    page_reflow_only_count: int
    substantive_changes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_sections_v1": self.total_sections_v1,
            "total_sections_v2": self.total_sections_v2,
            "added_count": self.added_count,
            "removed_count": self.removed_count,
            "modified_count": self.modified_count,
            "unchanged_count": self.unchanged_count,
            "page_reflow_only_count": self.page_reflow_only_count,
            "substantive_changes": self.substantive_changes,
        }


@dataclass
class DocumentComparisonResult:
    v1_path: str
    v2_path: str
    section_diffs: List[SectionDiff]
    added_sections: List[SectionDiff]
    removed_sections: List[SectionDiff]
    modified_sections: List[SectionDiff]
    unchanged_sections: List[SectionDiff]
    page_reflow_only_sections: List[SectionDiff]
    summary: ComparisonSummary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "v1_path": self.v1_path,
            "v2_path": self.v2_path,
            "summary": self.summary.to_dict(),
            "added": [s.to_dict() for s in self.added_sections],
            "removed": [s.to_dict() for s in self.removed_sections],
            "modified": [s.to_dict() for s in self.modified_sections],
            "page_reflow_only": [s.to_dict() for s in self.page_reflow_only_sections],
        }
