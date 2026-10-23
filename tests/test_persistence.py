"""
Unit tests for app/db/ and app/services/ (Step 4: Persistence and Database Integration).

Verifies:
1. SQLite schema creation and tables.
2. Relationships between ManualVersion and SectionRecords.
3. Idempotent ingestion (re-running ingestion creates no duplicate manual or section records).
4. Persistence and retrieval of version comparisons and the 6 substantive changes.
5. Structured JSON QA document storage and retrieval.
6. Source content hash preservation and staleness detection against updated versions.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.comparison.diff import compare_hierarchies
from app.db.models import (
    ManualVersion,
    SavedQASelection,
    SectionDiffRecord,
    SectionRecord,
    VersionComparisonRecord,
)
from app.db.qa_store import JSONFileQAStore
from app.db.session import Base, get_engine, get_session_factory, init_db
from app.hierarchy.builder import build_hierarchy
from app.parsing.extract import extract
from app.services.comparison import ComparisonService
from app.services.ingestion import IngestionService
from app.services.qa import QAService


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PDF_V1 = DATA_DIR / "ct200_manual.pdf"
PDF_V2 = DATA_DIR / "ct200_manual_v2.pdf"


@pytest.fixture
def db_session(tmp_path: Path):
    """Provides an isolated database session with freshly initialized schema."""
    db_file = tmp_path / "test_ct200.db"
    engine = get_engine(f"sqlite:///{db_file}")
    Base.metadata.create_all(bind=engine)
    session_factory = get_session_factory(engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture(scope="session")
def prebuilt_hier_v1():
    res = extract(str(PDF_V1))
    return build_hierarchy(res)


@pytest.fixture(scope="session")
def prebuilt_hier_v2():
    res = extract(str(PDF_V2))
    return build_hierarchy(res)


def test_schema_creation_and_tables(db_session: Session):
    """Verifies all expected tables and columns are created properly in SQLite."""
    engine = db_session.bind
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    expected_tables = {
        "manual_versions",
        "section_records",
        "version_comparisons",
        "section_diff_records",
        "saved_qa_selections",
    }
    assert expected_tables.issubset(set(table_names))

    # Verify column existence on section_records
    sec_cols = {col["name"] for col in inspector.get_columns("section_records")}
    assert {
        "id",
        "manual_version_id",
        "version_id",
        "section_number",
        "title",
        "content_hash",
        "order_index",
        "page_references",
        "normalized_text",
        "raw_text",
        "flags",
    }.issubset(sec_cols)


def test_ingest_manual_and_relationships(db_session: Session, prebuilt_hier_v1):
    """Verifies manual ingestion populates ManualVersion and SectionRecords with relationships."""
    ingestion = IngestionService()
    manual = ingestion.ingest_manual(
        pdf_path=PDF_V1,
        version_id="v1",
        session=db_session,
        hierarchy=prebuilt_hier_v1,
    )

    assert manual.id is not None
    assert manual.version_id == "v1"
    assert manual.total_sections == len(prebuilt_hier_v1.all_sections)
    assert len(manual.file_hash) == 64

    # Verify relationship and order index
    sections = manual.sections
    assert len(sections) == len(prebuilt_hier_v1.all_sections)

    # Inversion anomaly preserved: 3.4 precedes 3.3 in reading sequence
    sec_map = {s.section_number: s for s in sections}
    assert "3.4" in sec_map and "3.3" in sec_map
    assert sec_map["3.4"].order_index < sec_map["3.3"].order_index
    assert "out_of_order_physical_sequence" in sec_map["3.4"].flags

    # Depth skip preserved on 2.1.1.1
    assert sec_map["2.1.1.1"].numbering_depth == 4
    assert sec_map["2.1.1.1"].parent_number == "2.1"
    assert "numbering_level_skip" in sec_map["2.1.1.1"].flags

    # Table attribution
    assert len(sec_map["2.1"].tables) == 1
    assert len(sec_map["4.2"].tables) == 1
    assert sec_map["4.2"].tables[0]["rows"][0] == ["Code", "Meaning", "Device Behavior"]


def test_idempotent_ingestion(db_session: Session, prebuilt_hier_v1):
    """
    Verifies that calling ingest_manual repeatedly for the same version_id
    does not create duplicate ManualVersion or SectionRecord entries.
    """
    ingestion = IngestionService()

    # First ingestion
    m1 = ingestion.ingest_manual(PDF_V1, "v1", db_session, hierarchy=prebuilt_hier_v1)
    v1_id = m1.id
    initial_manual_count = db_session.query(ManualVersion).count()
    initial_section_count = db_session.query(SectionRecord).count()

    # Second ingestion without force
    m2 = ingestion.ingest_manual(PDF_V1, "v1", db_session, hierarchy=prebuilt_hier_v1)
    assert m2.id == v1_id
    assert db_session.query(ManualVersion).count() == initial_manual_count
    assert db_session.query(SectionRecord).count() == initial_section_count

    # Third ingestion with force=True
    m3 = ingestion.ingest_manual(PDF_V1, "v1", db_session, force=True, hierarchy=prebuilt_hier_v1)
    assert db_session.query(ManualVersion).count() == initial_manual_count
    assert db_session.query(SectionRecord).count() == initial_section_count
    assert len(m3.sections) == len(prebuilt_hier_v1.all_sections)


def test_comparison_persistence_and_substantive_changes(
    db_session: Session,
    prebuilt_hier_v1,
    prebuilt_hier_v2,
):
    """
    Verifies that running ComparisonService persists DocumentComparator results,
    including the summary and exactly 6 substantive changes.
    """
    ingestion = IngestionService()
    ingestion.ingest_manual(PDF_V1, "v1", db_session, hierarchy=prebuilt_hier_v1)
    ingestion.ingest_manual(PDF_V2, "v2", db_session, hierarchy=prebuilt_hier_v2)

    comp_service = ComparisonService()
    comp_rec = comp_service.compare_and_persist(
        v1_version_id="v1",
        v2_version_id="v2",
        hier_v1=prebuilt_hier_v1,
        hier_v2=prebuilt_hier_v2,
        session=db_session,
    )

    assert comp_rec.id is not None
    assert comp_rec.v1_version_id == "v1"
    assert comp_rec.v2_version_id == "v2"

    summary = comp_rec.summary
    assert summary["added_count"] == 1
    assert summary["removed_count"] == 0
    assert summary["modified_count"] == 4
    assert len(summary["substantive_changes"]) == 6

    # Verify persisted section diff records
    diff_records = (
        db_session.query(SectionDiffRecord)
        .filter_by(comparison_id=comp_rec.id)
        .all()
    )
    assert len(diff_records) > 0

    diff_map = {d.section_number: d for d in diff_records}

    # 1. 2.1.1.1 modified
    assert diff_map["2.1.1.1"].status == "modified"
    assert diff_map["2.1.1.1"].content_changed is True

    # 2. 3.2 modified
    assert diff_map["3.2"].status == "modified"
    assert diff_map["3.2"].content_changed is True

    # 3. 4.2 modified (table E3 modified, E6 added)
    assert diff_map["4.2"].status == "modified"
    assert diff_map["4.2"].table_diff is not None
    assert diff_map["4.2"].table_diff["added_count"] == 1
    assert diff_map["4.2"].table_diff["modified_count"] == 1

    # 4. 4.3 modified
    assert diff_map["4.3"].status == "modified"

    # 5. 5.3 added
    assert diff_map["5.3"].status == "added"
    assert diff_map["5.3"].title == "Data Export"

    # Section 8.1 reflow only
    assert diff_map["8.1"].status == "unchanged"
    assert diff_map["8.1"].content_changed is False
    assert diff_map["8.1"].page_changed is True
    assert diff_map["8.1"].v1_content_hash == diff_map["8.1"].v2_content_hash


def test_saved_qa_selection_and_qa_store(db_session: Session, tmp_path: Path, prebuilt_hier_v1):
    """
    Verifies creation of SavedQASelection, linking to JSON document in QA store,
    and storage/retrieval of structured QA payload.
    """
    ingestion = IngestionService()
    ingestion.ingest_manual(PDF_V1, "v1", db_session, hierarchy=prebuilt_hier_v1)

    qa_store = JSONFileQAStore(base_dir=tmp_path / "qa_store")
    qa_service = QAService(qa_store=qa_store)

    # 1. Create selection for Section 4.2
    selection = qa_service.create_selection("v1", "4.2", db_session)
    assert selection.id is not None
    assert selection.version_id == "v1"
    assert selection.section_number == "4.2"
    assert selection.section_title == "Error Codes"
    assert len(selection.source_content_hash) == 64
    assert selection.status == "pending"

    # 2. Save QA result
    qa_payload = {
        "questions_and_answers": [
            {
                "question": "What does error code E3 indicate?",
                "answer": "Overpressure detected; the cuff automatically deflates within 2 seconds.",
                "verification_status": "grounded",
            }
        ],
        "model": "gpt-4-simulation",
    }
    updated_sel, doc_id = qa_service.save_qa_result(selection.id, qa_payload, db_session)
    assert updated_sel.qa_result_id == doc_id
    assert updated_sel.status == "active"

    # 3. Retrieve from document store
    doc = qa_store.get(doc_id)
    assert doc is not None
    assert doc["version_id"] == "v1"
    assert doc["section_number"] == "4.2"
    assert doc["source_content_hash"] == selection.source_content_hash
    assert len(doc["questions_and_answers"]) == 1


def test_staleness_detection(
    db_session: Session,
    tmp_path: Path,
    prebuilt_hier_v1,
    prebuilt_hier_v2,
):
    """
    Verifies that SavedQASelection accurately detects staleness when content changes
    across versions (e.g. 2.1.1.1 or 4.2 modified in v2), but remains valid for
    unchanged content (e.g. Section 1 or Section 8.1).
    """
    ingestion = IngestionService()
    ingestion.ingest_manual(PDF_V1, "v1", db_session, hierarchy=prebuilt_hier_v1)
    ingestion.ingest_manual(PDF_V2, "v2", db_session, hierarchy=prebuilt_hier_v2)

    qa_store = JSONFileQAStore(base_dir=tmp_path / "qa_store")
    qa_service = QAService(qa_store=qa_store)

    # Case A: Unchanged section across versions (Section 1)
    sel_1 = qa_service.create_selection("v1", "1", db_session)
    stale_report_1 = qa_service.check_staleness(sel_1.id, db_session, target_version_id="v2")
    assert stale_report_1["is_stale"] is False
    assert "matches" in stale_report_1["reason"]

    # Case B: Modified section across versions (Section 2.1.1.1)
    sel_mod = qa_service.create_selection("v1", "2.1.1.1", db_session)
    stale_report_mod = qa_service.check_staleness(sel_mod.id, db_session, target_version_id="v2")
    assert stale_report_mod["is_stale"] is True
    assert stale_report_mod["source_content_hash"] != stale_report_mod["current_content_hash"]
    assert "Content changed" in stale_report_mod["reason"]

    # Case C: Modified table in Section 4.2
    sel_42 = qa_service.create_selection("v1", "4.2", db_session)
    stale_report_42 = qa_service.check_staleness(sel_42.id, db_session, target_version_id="v2")
    assert stale_report_42["is_stale"] is True


def test_json_qa_store_crud(tmp_path: Path):
    """Verifies basic CRUD operations on JSONFileQAStore."""
    store = JSONFileQAStore(base_dir=tmp_path / "store_test")

    # Save
    doc = {"version_id": "v1", "section_number": "1", "data": "hello"}
    doc_id = store.save(doc)
    assert doc_id.startswith("qa_")

    # Get
    retrieved = store.get(doc_id)
    assert retrieved is not None
    assert retrieved["data"] == "hello"

    # List
    all_docs = store.list_all(version_id="v1")
    assert len(all_docs) == 1

    # Delete
    assert store.delete(doc_id) is True
    assert store.get(doc_id) is None
    assert store.delete(doc_id) is False
