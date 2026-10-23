"""
Unit tests for app/parsing/extract.py.

Verifies:
1. Repetition-based header/footer detection on a synthetic fixture.
2. discarded_blocks == [] on actual data/ct200_manual.pdf and data/ct200_manual_v2.pdf.
3. Clean table extraction (1 table on P2 with 8 rows; 1 table on P4 with 6/7 rows).
4. Table headers are excluded from heading candidates.
5. 3-line document title is merged into a single H0 block.
6. Cross-page sentence stitching on non-terminal punctuation and prepositions.
7. normalize_text() with NFKC, U+2011/U+2010 mapping, and ligature expansion.
8. Character coverage check ratio >= 0.98.
"""

from __future__ import annotations

import os
from pathlib import Path

import fitz  # PyMuPDF
import pytest

from app.parsing.extract import PDFExtractor, TableBlock, extract, normalize_text


@pytest.fixture
def synthetic_pdf_with_headers_footers(tmp_path: Path) -> Path:
    """Creates a 3-page synthetic PDF containing repeated running headers and footers."""
    doc = fitz.open()
    header_text = "CardioTrack Technical Documentation Series"
    footer_text = "Confidential - Medical Device Reference"

    for i in range(3):
        # A5 page: 420 x 595 pt
        page = doc.new_page(width=420.0, height=595.0)

        # Insert running header at y=25pt (inside margin threshold <= 40pt)
        page.insert_text((33.0, 25.0), header_text, fontsize=9.0)

        # Insert page-specific body text
        page.insert_text((33.0, 150.0), f"Section {i+1} Unique Document Content", fontsize=14.0)
        page.insert_text((33.0, 180.0), f"This is synthetic page {i+1} body content for testing.", fontsize=11.0)

        # Insert running footer at y=575pt (inside margin threshold >= 555pt)
        page.insert_text((33.0, 575.0), footer_text, fontsize=9.0)

    pdf_file = tmp_path / "synthetic_hf.pdf"
    doc.save(str(pdf_file))
    doc.close()
    return pdf_file


def test_text_normalization():
    """Verifies NFKC normalization, U+2011/U+2010 mapping, and whitespace collapsing."""
    raw = "CardioTrack\u00a0CT\u2011200\tHome   Blood\u2010Pressure \ufb01eld \ufb00"
    norm = normalize_text(raw)
    assert norm == "CardioTrack CT-200 Home Blood-Pressure field ff"
    assert "\u2011" not in norm
    assert "\u2010" not in norm
    assert "\ufb01" not in norm
    assert "\ufb00" not in norm


def test_synthetic_header_footer_detection(synthetic_pdf_with_headers_footers: Path):
    """Proves that repetition-based header/footer detection identifies and discards repeated headers/footers."""
    extractor = PDFExtractor(header_margin_pt=40.0, footer_margin_pt=40.0)
    result = extractor.extract_document(synthetic_pdf_with_headers_footers)

    assert len(result.discarded_blocks) >= 6  # 3 headers + 3 footers
    discarded_texts = {d.text for d in result.discarded_blocks}
    assert "CardioTrack Technical Documentation Series" in discarded_texts
    assert "Confidential - Medical Device Reference" in discarded_texts

    # Verify body text is preserved and not discarded
    body_texts = " ".join(b.text for b in result.blocks)
    assert "Section 1 Unique Document Content" in body_texts
    assert "Section 2 Unique Document Content" in body_texts
    assert "Section 3 Unique Document Content" in body_texts


def test_real_pdfs_have_zero_discarded_headers_footers():
    """Asserts that discarded_blocks == [] on the actual CT-200 PDF manuals."""
    res_v1 = extract("data/ct200_manual.pdf")
    assert res_v1.discarded_blocks == []
    assert res_v1.coverage_report["discarded_count"] == 0

    res_v2 = extract("data/ct200_manual_v2.pdf")
    assert res_v2.discarded_blocks == []
    assert res_v2.coverage_report["discarded_count"] == 0


def test_table_extraction_and_heading_exclusion():
    """
    Verifies that:
    1. Exactly 1 table is extracted on Page 2 (8 rows).
    2. Exactly 1 table is extracted on Page 4 (6 rows in v1, 7 rows in v2).
    3. Table column headers ('Parameter', 'Value', 'Code', 'Meaning') are NOT emitted as headings.
    """
    res_v1 = extract("data/ct200_manual.pdf")
    assert len(res_v1.tables) == 2

    t_p2_v1 = next(t for t in res_v1.tables if t.page_number == 2)
    assert t_p2_v1.num_rows == 8
    assert t_p2_v1.num_cols == 2
    assert t_p2_v1.rows[0] == ["Parameter", "Value"]
    assert t_p2_v1.quality == "clean"

    t_p4_v1 = next(t for t in res_v1.tables if t.page_number == 4)
    assert t_p4_v1.num_rows == 6
    assert t_p4_v1.num_cols == 3
    assert t_p4_v1.rows[0] == ["Code", "Meaning", "Device Behavior"]
    assert t_p4_v1.rows[1][0] == "E1"
    assert t_p4_v1.rows[5][0] == "E5"

    res_v2 = extract("data/ct200_manual_v2.pdf")
    t_p4_v2 = next(t for t in res_v2.tables if t.page_number == 4)
    assert t_p4_v2.num_rows == 7
    assert t_p4_v2.rows[6][0] == "E6"

    # Verify that table headers are never in the heading list
    heading_texts = [b.text for b in res_v1.blocks if b.block_type == "heading"]
    for false_heading in ["Parameter", "Value", "Code", "Meaning", "Device Behavior"]:
        assert false_heading not in heading_texts


def test_title_merging():
    """Verifies that the 3-line document title on Page 1 is merged into a single H0 block."""
    for path in ["data/ct200_manual.pdf", "data/ct200_manual_v2.pdf"]:
        res = extract(path)
        title_blocks = [b for b in res.blocks if b.block_type == "title"]
        assert len(title_blocks) == 1
        t_block = title_blocks[0]
        assert t_block.heading_level == "H0"
        assert t_block.page_number == 1
        assert t_block.font_size == 22.0
        assert "CardioTrack CT-200 Home Blood Pressure Monitor" in t_block.text
        assert "Technical & User Manual" in t_block.text


def test_cross_page_stitching():
    """Verifies cross-page stitching behavior on non-terminal punctuation and prepositions."""
    res_v2 = extract("data/ct200_manual_v2.pdf")
    stitched_blocks = [b for b in res_v2.blocks if len(b.stitched_from_pages) > 1]
    assert len(stitched_blocks) >= 3

    # Check Section 4.3 stitch (P4 -> P5)
    s_43 = next(b for b in stitched_blocks if 4 in b.stitched_from_pages and 5 in b.stitched_from_pages)
    assert "except for E3 (overpressure), which cannot be silenced" in s_43.text

    # Check Section 6.1 stitch (P5 -> P6)
    s_61 = next(b for b in stitched_blocks if 5 in b.stitched_from_pages and 6 in b.stitched_from_pages)
    assert "and do not use alcohol, solvents, or abrasive cleaners" in s_61.text

    # Check Section 8.1 stitch (P6 -> P7)
    s_81 = next(b for b in stitched_blocks if 6 in b.stitched_from_pages and 7 in b.stitched_from_pages)
    assert "and has been validated against relevant clinical accuracy standards" in s_81.text


def test_character_coverage_check():
    """Verifies that the character coverage ratio is >= 0.98 on both documents."""
    for path in ["data/ct200_manual.pdf", "data/ct200_manual_v2.pdf"]:
        res = extract(path)
        cov = res.coverage_report
        assert cov["coverage_ratio"] >= 0.98
        assert cov["raw_total_chars"] > 6000
