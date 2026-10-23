"""
Hierarchy Builder.
Constructs section hierarchy trees from extraction outputs.

Key Guarantees:
- Uses numbering patterns (re.match) outside table regions.
- Preserves physical order_index; never reorders the document.
- Differentiates duplicate titles (e.g. 4.2 Error Codes vs 7.1 Error Codes).
- Identifies numbering depth skips (e.g. 2.1.1.1 skipping 2.1.1).
- Detects physical layout sequence inversions (e.g. Section 3.4 preceding 3.3).
- Correctly attributes body blocks, list items, and tables to their enclosing sections.
- Tracks empty bodies and heading-body page splits.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.hierarchy.models import DocumentHierarchy, SectionNode
from app.parsing.extract import Block, ExtractionResult, TableBlock


def parse_section_heading(text: str) -> Optional[Tuple[str, str]]:
    """
    Parses a numbered section heading string into (section_number, title).
    Handles both '1. Device Overview' and '2.1 General Specifications'.
    Example: '1. Device Overview' -> ('1', 'Device Overview')
    Example: '2.1.1.1 Battery Life Under Typical Use' -> ('2.1.1.1', 'Battery Life Under Typical Use')
    """
    m = re.match(r"^(\d+(?:\.\d+)*)\.?\s+([A-Z].*)", text.strip())
    if m:
        sec_num = m.group(1).strip()
        sec_title = m.group(2).strip()
        return sec_num, sec_title
    return None


def parse_numeric_tuple(sec_num: str) -> Tuple[int, ...]:
    """Converts dotted section number string to integer tuple for numerical comparison."""
    try:
        return tuple(int(p) for p in sec_num.split("."))
    except ValueError:
        return ()


class HierarchyBuilder:
    """Builds a DocumentHierarchy from an ExtractionResult."""

    def build(self, result: ExtractionResult) -> DocumentHierarchy:
        doc_title = ""
        doc_title_block: Optional[Block] = None

        all_sections: List[SectionNode] = []
        root_sections: List[SectionNode] = []
        sections_by_number: Dict[str, SectionNode] = {}
        detected_anomalies: List[Dict[str, Any]] = []

        # Hierarchy stack: list of tuples (depth, SectionNode)
        stack: List[Tuple[int, SectionNode]] = []
        order_counter = 0

        # Track previously seen section tuples at each parent level to detect inversions
        sibling_history: Dict[Optional[str], List[Tuple[int, ...]]] = {}

        for b in result.blocks:
            # 1. Capture document title
            if b.block_type == "title" and b.heading_level == "H0":
                doc_title = b.text
                doc_title_block = b
                continue

            # 2. Check if block is a section heading
            heading_info = None
            if not b.is_table_content and b.is_bold and b.block_type == "heading":
                heading_info = parse_section_heading(b.text)

            if heading_info:
                sec_num, sec_title = heading_info
                depth = len(sec_num.split("."))
                num_tuple = parse_numeric_tuple(sec_num)

                # Determine parent and attach according to stack
                level_skip_detected = False
                parent_node: Optional[SectionNode] = None

                # Pop stack while top has depth >= current depth
                # Exception: out-of-order siblings (like 3.4 then 3.3) have same depth, so pop to parent
                while stack and stack[-1][0] >= depth:
                    stack.pop()

                if stack:
                    parent_depth, parent_node = stack[-1]
                    if depth > parent_depth + 1:
                        level_skip_detected = True
                    hierarchy_level = parent_node.hierarchy_level + 1
                    parent_number = parent_node.section_number
                else:
                    hierarchy_level = 1
                    parent_number = None

                flags: List[str] = []
                if level_skip_detected:
                    flags.append("numbering_level_skip")
                    flags.append(f"skipped_intermediate_level_after_{parent_number}")
                    detected_anomalies.append({
                        "anomaly_type": "numbering_level_skip",
                        "section_number": sec_num,
                        "parent_number": parent_number,
                        "numbering_depth": depth,
                        "page_number": b.page_number,
                        "description": (
                            f"Section {sec_num} has numbering depth {depth} but directly attaches to "
                            f"parent {parent_number} (depth {parent_depth}), skipping intermediate levels."
                        ),
                    })

                # Check physical sequence inversion against preceding siblings
                parent_key = parent_number
                if parent_key not in sibling_history:
                    sibling_history[parent_key] = []

                prev_siblings = sibling_history[parent_key]
                if prev_siblings:
                    last_sibling_tuple = prev_siblings[-1]
                    if num_tuple < last_sibling_tuple:
                        flags.append("out_of_order_physical_sequence")
                        # Also tag the prior inverted sibling if not already tagged
                        prev_sec_str = ".".join(str(x) for x in last_sibling_tuple)
                        if prev_sec_str in sections_by_number:
                            if "out_of_order_physical_sequence" not in sections_by_number[prev_sec_str].flags:
                                sections_by_number[prev_sec_str].flags.append("out_of_order_physical_sequence")

                        detected_anomalies.append({
                            "anomaly_type": "physical_order_anomaly",
                            "section_number": sec_num,
                            "preceding_sibling": prev_sec_str,
                            "page_number": b.page_number,
                            "description": (
                                f"Section {sec_num} physically appears after Section {prev_sec_str} "
                                f"on page {b.page_number}, violating numerical ordering."
                            ),
                        })

                sibling_history[parent_key].append(num_tuple)

                node = SectionNode(
                    section_id=f"sec_{sec_num}",
                    section_number=sec_num,
                    title=sec_title,
                    hierarchy_level=hierarchy_level,
                    numbering_depth=depth,
                    order_index=order_counter,
                    parent_number=parent_number,
                    heading_block=b,
                    page_references=[b.page_number],
                    flags=flags,
                )
                order_counter += 1

                if parent_node:
                    parent_node.children.append(node)
                else:
                    root_sections.append(node)

                all_sections.append(node)
                sections_by_number[sec_num] = node
                stack.append((depth, node))

            elif stack:
                # 3. Non-heading block: attach to currently active section
                active_node = stack[-1][1]
                if b.block_type == "table":
                    if b.table_data and b.table_data not in active_node.tables:
                        active_node.tables.append(b.table_data)
                else:
                    active_node.body_blocks.append(b)

        # 4. Post-processing: check empty bodies, page breaks, and finalize page references
        for sec in all_sections:
            pages = set(sec.page_references)
            if sec.heading_block:
                pages.update(sec.heading_block.stitched_from_pages)

            for b in sec.body_blocks:
                pages.add(b.page_number)
                pages.update(b.stitched_from_pages)

            for t in sec.tables:
                pages.add(t.page_number)

            sec.page_references = sorted(list(pages))

            # Empty body check
            if not sec.body_blocks and not sec.tables:
                sec.flags.append("empty_body")

            # Check if heading is separated from body by page break
            if sec.heading_block and sec.body_blocks:
                first_body_page = sec.body_blocks[0].page_number
                if first_body_page > sec.heading_block.page_number:
                    sec.flags.append("separated_by_page_break")
                    detected_anomalies.append({
                        "anomaly_type": "heading_body_page_split",
                        "section_number": sec.section_number,
                        "heading_page": sec.heading_block.page_number,
                        "first_body_page": first_body_page,
                        "description": (
                            f"Section {sec.section_number} heading is on page {sec.heading_block.page_number}, "
                            f"but its initial body content begins on page {first_body_page}."
                        ),
                    })

        return DocumentHierarchy(
            document_path=result.document_path,
            title=doc_title,
            title_block=doc_title_block,
            root_sections=root_sections,
            all_sections=all_sections,
            sections_by_number=sections_by_number,
            detected_anomalies=detected_anomalies,
        )


def build_hierarchy(result: ExtractionResult) -> DocumentHierarchy:
    """Convenience entry point for building document hierarchy."""
    builder = HierarchyBuilder()
    return builder.build(result)
