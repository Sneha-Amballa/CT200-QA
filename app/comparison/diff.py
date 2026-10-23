"""
Document Version Comparison Engine.

Aligns section nodes using section numbering and parent-aware hierarchy keys.
Compares normalized content, table structures (cell-by-cell), and page references,
strictly separating content modifications from page reflows.
"""

from __future__ import annotations

import difflib
from typing import Any, Dict, List, Optional, Tuple

from app.comparison.models import (
    ComparisonSummary,
    DocumentComparisonResult,
    SectionDiff,
    TableDiff,
    TableRowDiff,
)
from app.hierarchy.models import DocumentHierarchy, SectionNode
from app.parsing.extract import TableBlock


def compare_tables(
    tables_v1: List[TableBlock],
    tables_v2: List[TableBlock],
    section_number: str,
) -> Optional[TableDiff]:
    """
    Compares table rows structurally across versions.
    Uses first column (e.g. 'Code' or 'Parameter') as row key where available.
    """
    if not tables_v1 and not tables_v2:
        return None

    t1 = tables_v1[0] if tables_v1 else None
    t2 = tables_v2[0] if tables_v2 else None

    if t1 is None or t2 is None:
        # Table added or removed
        return TableDiff(
            table_id=t2.table_id if t2 else (t1.table_id if t1 else "unknown"),
            section_number=section_number,
            has_changes=True,
        )

    # Build key-indexed row maps
    # Use first non-empty cell in row as key
    def make_row_map(table: TableBlock) -> Dict[str, List[str]]:
        row_map = {}
        for r_idx, row in enumerate(table.rows):
            key = row[0].strip() if row and row[0].strip() else f"row_{r_idx}"
            # Normalize whitespace within key
            key = " ".join(key.split())
            row_map[key] = row
        return row_map

    rows1 = make_row_map(t1)
    rows2 = make_row_map(t2)

    row_diffs: List[TableRowDiff] = []
    added_rows: List[TableRowDiff] = []
    removed_rows: List[TableRowDiff] = []
    modified_rows: List[TableRowDiff] = []

    all_keys = list(dict.fromkeys(list(rows1.keys()) + list(rows2.keys())))

    for k in all_keys:
        r1 = rows1.get(k)
        r2 = rows2.get(k)

        if r1 is not None and r2 is None:
            r_diff = TableRowDiff(
                row_key=k,
                change_type="removed",
                v1_cells=r1,
                v2_cells=None,
                description=f"Row '{k}' was removed in v2.",
            )
            row_diffs.append(r_diff)
            removed_rows.append(r_diff)
        elif r1 is None and r2 is not None:
            r_diff = TableRowDiff(
                row_key=k,
                change_type="added",
                v1_cells=None,
                v2_cells=r2,
                description=f"Row '{k}' was added in v2: {' | '.join(r2)}",
            )
            row_diffs.append(r_diff)
            added_rows.append(r_diff)
        else:
            # Both exist: check cells
            cell_diffs = {}
            for col_idx in range(max(len(r1), len(r2))):
                c1 = " ".join(r1[col_idx].split()) if col_idx < len(r1) else ""
                c2 = " ".join(r2[col_idx].split()) if col_idx < len(r2) else ""
                if c1 != c2:
                    cell_diffs[col_idx] = (c1, c2)

            if cell_diffs:
                desc_parts = [
                    f"Col {col}: '{pair[0]}' -> '{pair[1]}'"
                    for col, pair in cell_diffs.items()
                ]
                r_diff = TableRowDiff(
                    row_key=k,
                    change_type="modified",
                    v1_cells=r1,
                    v2_cells=r2,
                    cell_diffs=cell_diffs,
                    description=f"Row '{k}' modified: {'; '.join(desc_parts)}",
                )
                row_diffs.append(r_diff)
                modified_rows.append(r_diff)
            else:
                row_diffs.append(
                    TableRowDiff(
                        row_key=k,
                        change_type="unchanged",
                        v1_cells=r1,
                        v2_cells=r2,
                    )
                )

    has_changes = bool(added_rows or removed_rows or modified_rows)

    return TableDiff(
        table_id=t2.table_id if t2 else t1.table_id,
        section_number=section_number,
        has_changes=has_changes,
        row_diffs=row_diffs,
        added_rows=added_rows,
        removed_rows=removed_rows,
        modified_rows=modified_rows,
    )


def compute_word_diff(text_a: str, text_b: str) -> str:
    """Computes a readable word-level diff string using difflib.ndiff."""
    words_a = text_a.split()
    words_b = text_b.split()
    diff = list(difflib.ndiff(words_a, words_b))
    diff_words = [d for d in diff if d.startswith("+ ") or d.startswith("- ")]
    return " ".join(diff_words)


class DocumentComparator:
    """Compares two DocumentHierarchy instances and emits structured diffs."""

    def compare(
        self,
        hier_v1: DocumentHierarchy,
        hier_v2: DocumentHierarchy,
    ) -> DocumentComparisonResult:
        v1_map = hier_v1.sections_by_number
        v2_map = hier_v2.sections_by_number

        # Establish canonical aligned ordering
        ordered_keys: List[str] = []
        for s in hier_v1.all_sections:
            ordered_keys.append(s.section_number)

        for s in hier_v2.all_sections:
            if s.section_number not in ordered_keys:
                # Insert added section near its preceding sibling
                ordered_keys.append(s.section_number)

        section_diffs: List[SectionDiff] = []
        added_sections: List[SectionDiff] = []
        removed_sections: List[SectionDiff] = []
        modified_sections: List[SectionDiff] = []
        unchanged_sections: List[SectionDiff] = []
        page_reflow_only_sections: List[SectionDiff] = []

        substantive_changes: List[str] = []

        for sec_num in ordered_keys:
            s1 = v1_map.get(sec_num)
            s2 = v2_map.get(sec_num)

            if s1 is None and s2 is not None:
                # Added section
                diff_obj = SectionDiff(
                    section_number=sec_num,
                    title=s2.title,
                    status="added",
                    content_changed=True,
                    page_changed=True,
                    v1_pages=[],
                    v2_pages=s2.page_references,
                    v1_content_hash=None,
                    v2_content_hash=s2.content_hash(),
                    v1_normalized_text=None,
                    v2_normalized_text=s2.get_normalized_text(),
                    v1_raw_text=None,
                    v2_raw_text=s2.get_raw_text(),
                    word_diff=f"+ {s2.get_normalized_text()}",
                    explanation=f"New section added in v2 on page(s) {s2.page_references}.",
                )
                section_diffs.append(diff_obj)
                added_sections.append(diff_obj)
                substantive_changes.append(f"Section {sec_num} ({s2.title}) was added in v2.")

            elif s1 is not None and s2 is None:
                # Removed section
                diff_obj = SectionDiff(
                    section_number=sec_num,
                    title=s1.title,
                    status="removed",
                    content_changed=True,
                    page_changed=True,
                    v1_pages=s1.page_references,
                    v2_pages=[],
                    v1_content_hash=s1.content_hash(),
                    v2_content_hash=None,
                    v1_normalized_text=s1.get_normalized_text(),
                    v2_normalized_text=None,
                    v1_raw_text=s1.get_raw_text(),
                    v2_raw_text=None,
                    word_diff=f"- {s1.get_normalized_text()}",
                    explanation="Section was removed in v2.",
                )
                section_diffs.append(diff_obj)
                removed_sections.append(diff_obj)
                substantive_changes.append(f"Section {sec_num} ({s1.title}) was removed in v2.")

            elif s1 is not None and s2 is not None:
                # Section present in both versions
                page_changed = (s1.page_references != s2.page_references)

                # Structural table comparison
                tbl_diff = compare_tables(s1.tables, s2.tables, sec_num)

                norm1 = s1.get_normalized_text()
                norm2 = s2.get_normalized_text()
                hash1 = s1.content_hash()
                hash2 = s2.content_hash()

                text_changed = (hash1 != hash2)
                table_changed = bool(tbl_diff and tbl_diff.has_changes)
                content_changed = text_changed or table_changed

                if content_changed:
                    status = "modified"
                    w_diff = compute_word_diff(norm1, norm2)

                    explanations = []
                    if text_changed:
                        explanations.append("Body prose or parameters modified.")
                    if table_changed and tbl_diff:
                        if tbl_diff.modified_rows:
                            for mr in tbl_diff.modified_rows:
                                explanations.append(mr.description)
                        if tbl_diff.added_rows:
                            for ar in tbl_diff.added_rows:
                                explanations.append(ar.description)

                    expl_str = "; ".join(explanations)
                    diff_obj = SectionDiff(
                        section_number=sec_num,
                        title=s2.title,
                        status=status,
                        content_changed=True,
                        page_changed=page_changed,
                        v1_pages=s1.page_references,
                        v2_pages=s2.page_references,
                        v1_content_hash=hash1,
                        v2_content_hash=hash2,
                        v1_normalized_text=norm1,
                        v2_normalized_text=norm2,
                        v1_raw_text=s1.get_raw_text(),
                        v2_raw_text=s2.get_raw_text(),
                        word_diff=w_diff,
                        table_diff=tbl_diff,
                        explanation=expl_str,
                    )
                    section_diffs.append(diff_obj)
                    modified_sections.append(diff_obj)

                    # Detail substantive changes
                    if table_changed and tbl_diff:
                        for mr in tbl_diff.modified_rows:
                            substantive_changes.append(f"Section {sec_num} table: {mr.description}")
                        for ar in tbl_diff.added_rows:
                            substantive_changes.append(f"Section {sec_num} table: {ar.description}")
                    if text_changed and not table_changed:
                        substantive_changes.append(f"Section {sec_num} ({s2.title}): {w_diff[:100]}...")

                else:
                    status = "unchanged"
                    diff_obj = SectionDiff(
                        section_number=sec_num,
                        title=s2.title,
                        status=status,
                        content_changed=False,
                        page_changed=page_changed,
                        v1_pages=s1.page_references,
                        v2_pages=s2.page_references,
                        v1_content_hash=hash1,
                        v2_content_hash=hash2,
                        v1_normalized_text=norm1,
                        v2_normalized_text=norm2,
                        v1_raw_text=s1.get_raw_text(),
                        v2_raw_text=s2.get_raw_text(),
                        word_diff=None,
                        table_diff=tbl_diff,
                        explanation="Content is 100% identical across versions.",
                    )
                    section_diffs.append(diff_obj)
                    unchanged_sections.append(diff_obj)

                    if page_changed:
                        page_reflow_only_sections.append(diff_obj)

        summary = ComparisonSummary(
            total_sections_v1=len(hier_v1.all_sections),
            total_sections_v2=len(hier_v2.all_sections),
            added_count=len(added_sections),
            removed_count=len(removed_sections),
            modified_count=len(modified_sections),
            unchanged_count=len(unchanged_sections),
            page_reflow_only_count=len(page_reflow_only_sections),
            substantive_changes=substantive_changes,
        )

        return DocumentComparisonResult(
            v1_path=hier_v1.document_path,
            v2_path=hier_v2.document_path,
            section_diffs=section_diffs,
            added_sections=added_sections,
            removed_sections=removed_sections,
            modified_sections=modified_sections,
            unchanged_sections=unchanged_sections,
            page_reflow_only_sections=page_reflow_only_sections,
            summary=summary,
        )


def compare_hierarchies(
    hier_v1: DocumentHierarchy,
    hier_v2: DocumentHierarchy,
) -> DocumentComparisonResult:
    """Convenience function to compare two document hierarchies."""
    comparator = DocumentComparator()
    return comparator.compare(hier_v1, hier_v2)
