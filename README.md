# CardioTrack CT-200 Technical Documentation QA System

A specialized system for parsing, structuring, comparing, persisting, and querying technical manuals for the **CardioTrack CT-200 Home Blood Pressure Monitor** across product revisions (`v1` and `v2`).

---

## Architecture Overview

```text
ct200-qa/
├── app/
│   ├── main.py         # Step 5: FastAPI application entry point, lifecycle, and middleware
│   ├── api/            # Step 5: Route handlers (manuals, comparisons, selections), schemas, dependencies
│   ├── parsing/        # Step 2: PDF extraction layer (PyMuPDF, NFKC, bounding box table isolation, stitching)
│   ├── hierarchy/      # Step 3: Section hierarchy tree builder, anomaly detection, SHA-256 content hashing
│   ├── comparison/     # Step 3: Version comparison engine, word diffing, table row/cell diffing
│   ├── db/             # Step 4: SQLAlchemy models, SQLite connection/session, and abstract QA store
│   └── services/       # Step 4: Idempotent manual ingestion, comparison persistence, QA selection & staleness
├── data/
│   ├── ct200_manual.pdf     # Revision 1 manual (6 pages, A5 portrait)
│   ├── ct200_manual_v2.pdf  # Revision 2 manual (7 pages, A5 portrait)
│   ├── ct200.db             # Default SQLite persistent database
│   ├── uploads/             # Securely stored uploaded PDF manuals
│   └── qa_store/            # JSON-backed structured QA output store
├── docs/
│   ├── irregularities.md    # Detailed audit of structural irregularities and physical coordinates
│   └── inspection/          # Automated extraction inspection reports and JSON findings
├── scripts/
│   ├── inspect_pdf.py       # PDF inspection utility
│   └── ocr_crosscheck.py    # Dual OCR cross-check against PyMuPDF text spans
└── tests/
    ├── test_api.py          # Step 5: FastAPI endpoint integration tests (10 tests)
    ├── test_extract.py      # Step 2: Tests for extraction, table isolation, title merging, stitching (7 tests)
    ├── test_hierarchy.py    # Step 3: Tests for hierarchy building, anomalies (3.4 before 3.3, skip), duplicate titles (8 tests)
    ├── test_comparison.py   # Step 3: Tests for 8.1 hash equality, exactly 6 substantive changes, reflow isolation (10 tests)
    └── test_persistence.py  # Step 4: Tests for SQLite schema, idempotent ingestion, comparison persistence, and staleness (7 tests)
```

---

## REST API (Step 5)

### Running the API Server

Start the development server with auto-reload:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive OpenAPI documentation is available at:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Application health check and version metadata. |
| `POST` | `/manuals/ingest` | Upload a manual PDF and ingest into database idempotently. |
| `GET` | `/manuals` | List all ingested manual versions. |
| `GET` | `/manuals/{version_id}/sections` | Paginated listing of section nodes for a manual version. |
| `GET` | `/manuals/{version_id}/sections/{section_number}` | Retrieve full section content, body blocks, and tables. |
| `GET` | `/manuals/{version_id}/search?q=...` | Search section titles and normalized body prose. |
| `POST` | `/comparisons` | Run and persist a structural comparison between two versions. |
| `GET` | `/comparisons/{comparison_id}` | Retrieve comparison results, table diffs, and substantive changes. |
| `POST` | `/selections` | Create a QA selection pinned to a manual section and content hash. |
| `GET` | `/selections/{selection_id}/staleness?target_version=...` | Evaluate if a selection's content hash remains current or is stale. |
| `POST` | `/selections/{selection_id}/generate-qa` | API contract for LLM generation (reports 501 until Step 6). |

### Example API Requests

#### 1. Ingest Manual
```bash
curl -X POST "http://localhost:8000/manuals/ingest" \
  -F "file=@data/ct200_manual.pdf" \
  -F "version_id=v1"
```

#### 2. Search Section Content
```bash
curl "http://localhost:8000/manuals/v1/search?q=overpressure"
```

#### 3. Compare Manual Versions
```bash
curl -X POST "http://localhost:8000/comparisons" \
  -H "Content-Type: application/json" \
  -d '{"v1_version_id": "v1", "v2_version_id": "v2"}'
```

#### 4. Create Selection & Check Staleness
```bash
# Create selection for section 2.1.1.1 in v1
curl -X POST "http://localhost:8000/selections" \
  -H "Content-Type: application/json" \
  -d '{"version_id": "v1", "section_number": "2.1.1.1"}'

# Check staleness against v2 (detects battery cycle change 300 -> 250)
curl "http://localhost:8000/selections/{selection_id}/staleness?target_version=v2"
```

---

## Setup & Installation

### Requirements
- Python 3.11+ (tested on Python 3.13)
- SQLite (built into Python standard library)

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

Run all 42 automated tests across all modules:

```bash
python -m pytest -v tests/
```

Run specific test modules:
```bash
# Test FastAPI REST API layer (Step 5)
python -m pytest -v tests/test_api.py

# Test persistence, database schema, and staleness (Step 4)
python -m pytest -v tests/test_persistence.py

# Test version comparison and diffing (Step 3)
python -m pytest -v tests/test_comparison.py

# Test hierarchy builder and anomalies (Step 3)
python -m pytest -v tests/test_hierarchy.py

# Test extraction layer (Step 2)
python -m pytest -v tests/test_extract.py
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
