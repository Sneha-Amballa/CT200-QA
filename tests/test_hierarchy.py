"""
Unit tests for app/hierarchy/ (Step 3).

Verifies:
1. Section hierarchy construction preserving physical document order.
2. Inversion anomaly: Section 3.4 physically preceding Section 3.3 (order preserved, flagged).
3. Numbering depth skip: Section 2.1.1.1 attached to parent 2.1 (depth=4, flagged).
4. Duplicate headings: 4.2 Error Codes vs 7.1 Error Codes are distinct nodes with distinct content.
5. Empty body: Section 2 has empty direct body and is flagged.
6. Heading-body page split: v2 Section 3.1 heading on P2 with body starting on P3 (flagged, pages=[2, 3]).
7. Table attribution: Specifications table attached to 2.1; Error Codes table attached to 4.2.
8. Serialization integrity (to_dict).
"""

from __future__ import annotations

from pathlib import Path
import pytest

from app.parsing.extract import extract
from app.hierarchy.builder import build_hierarchy, parse_section_heading
from app.hierarchy.models import DocumentHierarchy, SectionNode


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PDF_V1 = DATA_DIR / "ct200_manual.pdf"
PDF_V2 = DATA_DIR / "ct200_manual_v2.pdf"


@pytest.fixture(scope="session")
def hier_v1() -> DocumentHierarchy:
    res = extract(str(PDF_V1))
    return build_hierarchy(res)


@pytest.fixture(scope="session")
def hier_v2() -> DocumentHierarchy:
    res = extract(str(PDF_V2))
    return build_hierarchy(res)


def test_parse_section_heading():
    """Verifies regex parser extracts number and title correctly."""
    assert parse_section_heading("1. Device Overview") == ("1", "Device Overview")
    assert parse_section_heading("2.1 General Specifications") == ("2.1", "General Specifications")
    assert parse_section_heading("2.1.1.1 Battery Life Under Typical Use") == (
        "2.1.1.1",
        "Battery Life Under Typical Use",
    )
    assert parse_section_heading("3.4 Irregular Pulse Detection") == (
        "3.4",
        "Irregular Pulse Detection",
    )
    assert parse_section_heading("4.2 Error Codes") == ("4.2", "Error Codes")
    assert parse_section_heading("7.1 Error Codes") == ("7.1", "Error Codes")

    # Non-heading text should return None
    assert parse_section_heading("Normal: Cuff inflates smoothly.") is None
    assert parse_section_heading("This device is compliant.") is None


def test_physical_reading_order_preserved(hier_v1: DocumentHierarchy, hier_v2: DocumentHierarchy):
    """
    Verifies that all_sections strictly preserves document reading order
    and does NOT artificially sort sections numerically.
    In particular, 3.4 appears BEFORE 3.3 in both versions.
    """
    for hier in (hier_v1, hier_v2):
        sec_numbers = [s.section_number for s in hier.all_sections]
        assert "3.4" in sec_numbers
        assert "3.3" in sec_numbers

        idx_34 = sec_numbers.index("3.4")
        idx_33 = sec_numbers.index("3.3")

        # 3.4 must physically precede 3.3
        assert idx_34 < idx_33, f"Expected 3.4 before 3.3 in physical sequence, got: {sec_numbers}"

        sec_34 = hier.sections_by_number["3.4"]
        sec_33 = hier.sections_by_number["3.3"]

        assert sec_34.order_index < sec_33.order_index
        assert "out_of_order_physical_sequence" in sec_34.flags
        assert "out_of_order_physical_sequence" in sec_33.flags

        # Check detected anomalies list
        inversion_anomalies = [
            a for a in hier.detected_anomalies if a.get("anomaly_type") == "physical_order_anomaly"
        ]
        assert len(inversion_anomalies) >= 1
        assert inversion_anomalies[0]["section_number"] == "3.3"
        assert inversion_anomalies[0]["preceding_sibling"] == "3.4"


def test_numbering_level_skip_2_1_1_1(hier_v1: DocumentHierarchy, hier_v2: DocumentHierarchy):
    """
    Verifies Section 2.1.1.1 attaches directly to parent 2.1 (skipping 2.1.1).
    Checks numbering_depth=4, parent_number='2.1', and flag 'numbering_level_skip'.
    """
    for hier in (hier_v1, hier_v2):
        sec = hier.sections_by_number.get("2.1.1.1")
        assert sec is not None
        assert sec.title == "Battery Life Under Typical Use"
        assert sec.numbering_depth == 4
        assert sec.parent_number == "2.1"
        assert "numbering_level_skip" in sec.flags

        # Parent 2.1 must include 2.1.1.1 in children
        parent = hier.sections_by_number.get("2.1")
        assert parent is not None
        child_numbers = [c.section_number for c in parent.children]
        assert "2.1.1.1" in child_numbers

        # Check detected anomalies
        skip_anomalies = [
            a for a in hier.detected_anomalies if a.get("anomaly_type") == "numbering_level_skip"
        ]
        assert any(a["section_number"] == "2.1.1.1" for a in skip_anomalies)


def test_duplicate_headings_distinct_nodes(hier_v1: DocumentHierarchy, hier_v2: DocumentHierarchy):
    """
    Verifies that '4.2 Error Codes' and '7.1 Error Codes' are represented as distinct
    nodes with unique section numbers, parents, and distinct content.
    """
    for hier in (hier_v1, hier_v2):
        sec_42 = hier.sections_by_number.get("4.2")
        sec_71 = hier.sections_by_number.get("7.1")

        assert sec_42 is not None
        assert sec_71 is not None

        assert sec_42.title == "Error Codes"
        assert sec_71.title == "Error Codes"

        assert sec_42.section_number == "4.2"
        assert sec_71.section_number == "7.1"

        assert sec_42.parent_number == "4"
        assert sec_71.parent_number == "7"

        # Content must be completely different
        assert sec_42.content_hash() != sec_71.content_hash()
        assert len(sec_42.tables) == 1  # 4.2 has the error code table
        assert len(sec_71.tables) == 0  # 7.1 has troubleshooting guidance text


def test_empty_body_section_2(hier_v1: DocumentHierarchy, hier_v2: DocumentHierarchy):
    """
    Verifies that Section 2 ('Physical and Electrical Specifications') is treated
    cleanly as a parent section with an empty direct body.
    """
    for hier in (hier_v1, hier_v2):
        sec_2 = hier.sections_by_number.get("2")
        assert sec_2 is not None
        assert sec_2.title == "Physical and Electrical Specifications"
        assert "empty_body" in sec_2.flags
        assert len(sec_2.body_blocks) == 0
        assert len(sec_2.tables) == 0
        assert len(sec_2.children) >= 1  # Has subsection 2.1


def test_heading_body_page_split_v2(hier_v2: DocumentHierarchy):
    """
    Verifies that v2 Section 3.1 ('Powering On and Self-Test') heading appears on Page 2
    while its body content starts on Page 3, resulting in page_references=[2, 3] and
    the 'separated_by_page_break' flag.
    """
    sec_31 = hier_v2.sections_by_number.get("3.1")
    assert sec_31 is not None
    assert sec_31.heading_block.page_number == 2
    assert "separated_by_page_break" in sec_31.flags
    assert 2 in sec_31.page_references
    assert 3 in sec_31.page_references

    split_anomalies = [
        a for a in hier_v2.detected_anomalies if a.get("anomaly_type") == "heading_body_page_split"
    ]
    assert any(a["section_number"] == "3.1" for a in split_anomalies)


def test_table_attribution(hier_v1: DocumentHierarchy, hier_v2: DocumentHierarchy):
    """
    Verifies table blocks are properly attached to their enclosing sections:
    - Section 2.1 has the specifications table (8 rows).
    - Section 4.2 has the error codes table (6 rows in v1, 7 rows in v2).
    """
    for hier, expected_error_rows in [(hier_v1, 6), (hier_v2, 7)]:
        sec_21 = hier.sections_by_number.get("2.1")
        assert sec_21 is not None
        assert len(sec_21.tables) == 1
        assert len(sec_21.tables[0].rows) == 8
        assert sec_21.tables[0].rows[0] == ["Parameter", "Value"]

        sec_42 = hier.sections_by_number.get("4.2")
        assert sec_42 is not None
        assert len(sec_42.tables) == 1
        assert len(sec_42.tables[0].rows) == expected_error_rows
        assert sec_42.tables[0].rows[0] == ["Code", "Meaning", "Device Behavior"]


def test_hierarchy_serialization(hier_v1: DocumentHierarchy):
    """Verifies to_dict produces a valid recursive dictionary with all required keys."""
    d = hier_v1.to_dict()
    assert "document_path" in d
    assert "title" in d
    assert "total_sections" in d
    assert "root_sections" in d
    assert "anomalies" in d

    sec_d = hier_v1.sections_by_number["2.1"].to_dict()
    assert sec_d["section_number"] == "2.1"
    assert sec_d["parent_number"] == "2"
    assert sec_d["table_count"] == 1
    assert "content_hash" in sec_d
