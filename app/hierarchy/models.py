"""
Section Hierarchy Data Models.

Represents document structure, section nodes, hierarchy levels,
and metadata flags (empty body, level skip, physical sequence anomalies).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.parsing.extract import Block, TableBlock


@dataclass
class SectionNode:
    section_id: str                      # e.g. "sec_1", "sec_2.1", "sec_2.1.1.1", "sec_4.2", "sec_7.1"
    section_number: str                  # e.g. "1", "2.1", "2.1.1.1", "4.2", "7.1"
    title: str                           # e.g. "General Specifications", "Error Codes"
    hierarchy_level: int                 # Derived hierarchy level (1 for H1, 2 for H2, 3 for H3, etc.)
    numbering_depth: int                 # Dotted depth: len(section_number.split('.'))
    order_index: int                     # Physical reading sequence index (0-based)
    parent_number: Optional[str] = None # Section number of parent node
    children: List[SectionNode] = field(default_factory=list)
    body_blocks: List[Block] = field(default_factory=list)
    tables: List[TableBlock] = field(default_factory=list)
    heading_block: Optional[Block] = None
    page_references: List[int] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)

    def get_normalized_text(self) -> str:
        """
        Returns normalized text of heading, body blocks, and tables.
        Normalizes intra-paragraph line breaks to avoid false diffs from line wrapping.
        """
        parts = [f"{self.section_number} {self.title}"]
        for b in self.body_blocks:
            if b.text.strip():
                parts.append(b.text.strip())
        for t in self.tables:
            for row in t.rows:
                parts.append(" | ".join(row))
        # Normalize whitespace so line wrapping doesn't create phantom differences
        raw_joined = " ".join(parts)
        return " ".join(raw_joined.split())

    def get_raw_text(self) -> str:
        """Returns concatenated raw text with exact physical line breaks for auditing."""
        parts = []
        if self.heading_block:
            parts.append(self.heading_block.raw_text.strip())
        else:
            parts.append(f"{self.section_number} {self.title}")
        for b in self.body_blocks:
            if b.raw_text.strip():
                parts.append(b.raw_text.strip())
        for t in self.tables:
            for row in t.raw_rows:
                parts.append(" | ".join(row))
        return "\n".join(parts)

    def content_hash(self) -> str:
        """Computes SHA-256 hash of normalized section content for deterministic change detection."""
        norm = self.get_normalized_text()
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()

    def to_dict(self) -> Dict[str, Any]:
        """Serializes node to dictionary representation."""
        return {
            "section_id": self.section_id,
            "section_number": self.section_number,
            "title": self.title,
            "hierarchy_level": self.hierarchy_level,
            "numbering_depth": self.numbering_depth,
            "order_index": self.order_index,
            "parent_number": self.parent_number,
            "page_references": self.page_references,
            "flags": self.flags,
            "content_hash": self.content_hash(),
            "body_block_count": len(self.body_blocks),
            "table_count": len(self.tables),
            "children": [c.to_dict() for c in self.children],
        }


@dataclass
class DocumentHierarchy:
    document_path: str
    title: str
    title_block: Optional[Block]
    root_sections: List[SectionNode]
    all_sections: List[SectionNode]     # Flat list in physical reading order
    sections_by_number: Dict[str, SectionNode]
    detected_anomalies: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_path": self.document_path,
            "title": self.title,
            "total_sections": len(self.all_sections),
            "root_sections": [s.to_dict() for s in self.root_sections],
            "anomalies": self.detected_anomalies,
        }
