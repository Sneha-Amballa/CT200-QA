# CardioTrack CT-200 Technical Documentation QA System

A specialized system for parsing, structuring, comparing, and persisting technical manuals for the **CardioTrack CT-200 Home Blood Pressure Monitor** across product revisions (`v1` and `v2`).

---

## Architecture Overview

```text
ct200-qa/
├── app/
│   ├── parsing/        # Step 2: PDF extraction layer (PyMuPDF, NFKC, bounding box table isolation, stitching)
│   ├── hierarchy/      # Step 3: Section hierarchy tree builder, anomaly detection, SHA-256 content hashing
│   ├── comparison/     # Step 3: Version comparison engine, word diffing, table row/cell diffing
│   ├── db/             # Step 4: SQLAlchemy models, SQLite connection/session, and abstract QA store
│   └── services/       # Step 4: Idempotent manual ingestion, comparison persistence, QA selection & staleness
├── data/
│   ├── ct200_manual.pdf     # Revision 1 manual (6 pages, A5 portrait)
│   ├── ct200_manual_v2.pdf  # Revision 2 manual (7 pages, A5 portrait)
│   ├── ct200.db             # Default SQLite persistent database
│   └── qa_store/            # JSON-backed structured QA output store
├── docs/
│   ├── irregularities.md    # Detailed audit of structural irregularities and physical coordinates
│   └── inspection/          # Automated extraction inspection reports and JSON findings
├── scripts/
│   ├── inspect_pdf.py       # PDF inspection utility
│   └── ocr_crosscheck.py    # Dual OCR cross-check against PyMuPDF text spans
└── tests/
    ├── test_extract.py      # Tests for PDF extraction, table isolation, title merging, stitching
    ├── test_hierarchy.py    # Tests for hierarchy building, anomalies (3.4 before 3.3, 2.1.1.1 skip), duplicate titles
    ├── test_comparison.py   # Tests for 8.1 hash equality, exactly 6 substantive changes, page reflow isolation
    └── test_persistence.py  # Tests for SQLite schema, idempotent ingestion, comparison persistence, and staleness
```

---

## Database & Persistence Layer (Step 4)

### 1. Relational Models (SQLAlchemy + SQLite)
- **`manual_versions`**: Stores manual metadata (`version_id`, `filename`, `file_hash`, `title`, `total_pages`, `total_sections`, `ingested_at`, `source_metadata`).
- **`section_records`**: Stores section hierarchy nodes with physical sequence tracking (`order_index`), hierarchy depth (`numbering_depth`), page references (`page_references`), serialized body blocks (`body_blocks`), structured tables (`tables`), flags (`flags`), and normalized SHA-256 content hashes (`content_hash`).
- **`version_comparisons`**: Stores pairwise version comparisons with high-level statistics and substantive change logs.
- **`section_diff_records`**: Detailed per-section diffs distinguishing content changes (`status = "modified"`, `word_diff`, `table_diff`) from page reflows (`page_changed = True`, `content_changed = False`).
- **`saved_qa_selections`**: User/system selection records binding a target section and snapshotting `source_content_hash` at selection/generation time.

### 2. Document-Backed QA Repository
- **`BaseQADocumentStore`**: Abstract interface defining `save`, `get`, `list_all`, and `delete`.
- **`JSONFileQAStore`**: Clean, file-backed JSON implementation storing structured QA documents in `data/qa_store/<qa_id>.json`. Can be seamlessly swapped for MongoDB without changing consuming service code.

### 3. Service Layer
- **`IngestionService`**: Provides idempotent manual ingestion. Re-running ingestion for an existing `version_id` returns the existing record without creating duplicate entries or orphaned section rows. Supports `force=True` for clean re-ingestion.
- **`ComparisonService`**: Reuses the domain `DocumentComparator` and persists comparison results directly into SQLite.
- **`QAService`**: Tracks QA generation selections, links them to JSON documents, and provides automated **staleness detection** by comparing snapshot `source_content_hash` against target version section hashes.

---

## Setup & Installation

### Requirements
- Python 3.11+ (tested on Python 3.13)
- SQLite (included with standard Python)

### 1. Create Virtual Environment
```bash
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

---

## Running the Test Suite

Run all 32 automated tests across all four modules:

```bash
python -m pytest -v tests/
```

Run specific test modules:
```bash
# Test extraction layer (Step 2)
python -m pytest -v tests/test_extract.py

# Test hierarchy builder and anomalies (Step 3)
python -m pytest -v tests/test_hierarchy.py

# Test version comparison and diffing (Step 3)
python -m pytest -v tests/test_comparison.py

# Test persistence, database schema, and staleness (Step 4)
python -m pytest -v tests/test_persistence.py
```

---

## Substantive Version Changes Verified

The comparison and persistence layer detects and stores **exactly 6 substantive changes** between `ct200_manual.pdf` (v1) and `ct200_manual_v2.pdf` (v2):

1. **Section 2.1.1.1** (*Battery Life Under Typical Use*): Rated cycle count reduced from 300 cycles / 15% drop to 250 cycles / 10% drop (`modified`).
2. **Section 3.2** (*Cuff Inflation Sequence*): Re-inflation pressure step decreased from 40 mmHg increments to 30 mmHg increments (`modified`).
3. **Section 4.2** (*Error Codes Table*): Auto-deflation timer for error **E3** reduced from 2 seconds to 1.5 seconds (`modified`).
4. **Section 4.2** (*Error Codes Table*): Error **E6** (*Bluetooth sync failure*) added to table (`added`).
5. **Section 4.3** (*Alarm Thresholds*): Prose updated to reference error conditions **E1–E6** instead of E1–E5 (`modified`).
6. **Section 5.3** (*Data Export*): Brand-new section added in v2 covering Bluetooth and USB-C data export (`added`).

All other 15 sections are identical, with 6 sections undergoing **page reflow only** (e.g. Section 8.1 byte-for-byte SHA-256 hash match `4435bcff...`).
