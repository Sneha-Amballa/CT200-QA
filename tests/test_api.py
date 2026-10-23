"""
Unit and Integration Tests for FastAPI REST API (Step 5).

Verifies:
1. Health check endpoint (GET /health).
2. PDF upload and validation (POST /manuals/ingest).
3. Idempotent ingestion and version listing (GET /manuals).
4. Section hierarchy listing and detailed section retrieval (GET /manuals/{v}/sections/...).
5. Section content and title search (GET /manuals/{v}/search?q=...).
6. Version comparison creation and retrieval (POST /comparisons, GET /comparisons/{id}).
7. QA selection creation and cross-version staleness verification (POST /selections, GET /selections/{id}/staleness).
8. QA generation API contract reporting 501 Not Implemented (POST /selections/{id}/generate-qa).
9. Error handling: 400 Bad Request, 404 Not Found, 422 Validation Error.
"""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.dependencies import get_db_session
from app.db.models import Base
from app.main import app

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
PDF_V1 = DATA_DIR / "ct200_manual.pdf"
PDF_V2 = DATA_DIR / "ct200_manual_v2.pdf"


@pytest.fixture(scope="session")
def test_engine(tmp_path_factory):
    """Creates a temporary SQLite database engine for API tests."""
    temp_dir = tmp_path_factory.mktemp("api_db")
    db_file = temp_dir / "test_api_ct200.db"
    engine = create_engine(
        f"sqlite:///{db_file}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture(scope="session")
def test_session_factory(test_engine):
    return sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session")
def client(test_session_factory):
    """Provides a TestClient with dependency override for get_db_session."""
    def override_get_db():
        session = test_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db_session] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health_check(client: TestClient):
    """Verifies GET /health returns 200 OK and expected app metadata."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["app"] == "ct200-qa"
    assert data["version"] == "1.0.0"


def test_ingest_manual_validation_errors(client: TestClient):
    """Verifies upload validation: rejects non-PDFs and invalid version identifiers."""
    # 1. Reject non-PDF file
    resp = client.post(
        "/manuals/ingest",
        data={"version_id": "v1"},
        files={"file": ("notes.txt", b"Invalid content", "text/plain")},
    )
    assert resp.status_code == 400
    assert "Unsupported file type" in resp.json()["detail"]

    # 2. Reject invalid version identifier with invalid characters
    with open(PDF_V1, "rb") as f:
        resp = client.post(
            "/manuals/ingest",
            data={"version_id": "v1/invalid path"},
            files={"file": ("ct200_manual.pdf", f, "application/pdf")},
        )
    assert resp.status_code == 400
    assert "Invalid version_id" in resp.json()["detail"]


def test_ingest_manual_success_and_idempotency(client: TestClient):
    """Verifies successful ingestion of v1 manual and idempotent re-upload."""
    # 1. First upload
    with open(PDF_V1, "rb") as f:
        resp1 = client.post(
            "/manuals/ingest",
            data={"version_id": "v1"},
            files={"file": ("ct200_manual.pdf", f, "application/pdf")},
        )
    assert resp1.status_code == 201
    data1 = resp1.json()
    assert data1["version_id"] == "v1"
    assert data1["total_sections"] > 0
    assert len(data1["file_hash"]) == 64

    # 2. Second upload without force (idempotent return of same record)
    with open(PDF_V1, "rb") as f:
        resp2 = client.post(
            "/manuals/ingest",
            data={"version_id": "v1", "force": False},
            files={"file": ("ct200_manual.pdf", f, "application/pdf")},
        )
    assert resp2.status_code == 201
    data2 = resp2.json()
    assert data2["id"] == data1["id"]
    assert data2["file_hash"] == data1["file_hash"]

    # Ingest v2 for subsequent comparison tests
    with open(PDF_V2, "rb") as f:
        resp_v2 = client.post(
            "/manuals/ingest",
            data={"version_id": "v2"},
            files={"file": ("ct200_manual_v2.pdf", f, "application/pdf")},
        )
    assert resp_v2.status_code == 201


def test_list_manuals(client: TestClient):
    """Verifies GET /manuals lists ingested versions."""
    resp = client.get("/manuals")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 2
    version_ids = [m["version_id"] for m in data["manuals"]]
    assert "v1" in version_ids
    assert "v2" in version_ids


def test_list_sections(client: TestClient):
    """Verifies GET /manuals/{version_id}/sections returns section hierarchy list."""
    resp = client.get("/manuals/v1/sections")
    assert resp.status_code == 200
    data = resp.json()
    assert data["version_id"] == "v1"
    assert data["total_sections"] > 0
    sec_numbers = [s["section_number"] for s in data["sections"]]
    assert "1" in sec_numbers
    assert "2.1" in sec_numbers
    assert "4.2" in sec_numbers

    # Verify 404 for nonexistent version
    resp_404 = client.get("/manuals/nonexistent_version/sections")
    assert resp_404.status_code == 404


def test_get_section_detail(client: TestClient):
    """Verifies GET /manuals/{version_id}/sections/{section_number} returns full content and tables."""
    # Section 2.1 (Specification table)
    resp = client.get("/manuals/v1/sections/2.1")
    assert resp.status_code == 200
    sec_21 = resp.json()
    assert sec_21["section_number"] == "2.1"
    assert sec_21["title"] == "General Specifications"
    assert len(sec_21["tables"]) == 1
    assert sec_21["tables"][0]["rows"][0] == ["Parameter", "Value"]

    # Section 4.2 (Error codes table)
    resp_42 = client.get("/manuals/v1/sections/4.2")
    assert resp_42.status_code == 200
    sec_42 = resp_42.json()
    assert sec_42["section_number"] == "4.2"
    assert sec_42["title"] == "Error Codes"
    assert len(sec_42["tables"]) == 1

    # 404 for nonexistent section
    resp_404 = client.get("/manuals/v1/sections/99.9")
    assert resp_404.status_code == 404


def test_search_sections(client: TestClient):
    """Verifies GET /manuals/{version_id}/search searches titles and body prose."""
    # Search for "overpressure"
    resp = client.get("/manuals/v1/search?q=overpressure")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_results"] > 0
    matched_sections = [r["section_number"] for r in data["results"]]
    assert "4.2" in matched_sections or "4.3" in matched_sections

    # Search for "battery"
    resp_bat = client.get("/manuals/v1/search?q=battery")
    assert resp_bat.status_code == 200
    assert any("2.1" in r["section_number"] for r in resp_bat.json()["results"])

    # 400 for empty query
    resp_empty = client.get("/manuals/v1/search?q=   ")
    assert resp_empty.status_code == 400

    # 404 for nonexistent manual version
    resp_404 = client.get("/manuals/nonexistent/search?q=battery")
    assert resp_404.status_code == 404


def test_comparison_endpoints(client: TestClient):
    """Verifies POST /comparisons and GET /comparisons/{id} persist and retrieve version diffs."""
    # 1. Create comparison between v1 and v2
    resp = client.post(
        "/comparisons",
        json={"v1_version_id": "v1", "v2_version_id": "v2", "force": False},
    )
    assert resp.status_code == 201
    comp = resp.json()
    comp_id = comp["id"]
    assert comp["v1_version_id"] == "v1"
    assert comp["v2_version_id"] == "v2"
    assert comp["summary"]["modified_count"] == 4
    assert comp["summary"]["added_count"] == 1
    assert len(comp["substantive_changes"]) == 6

    # 2. Retrieve comparison by ID
    resp_get = client.get(f"/comparisons/{comp_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["id"] == comp_id

    # 3. Retrieve comparison by version pair key
    resp_pair = client.get("/comparisons/v1_v2")
    assert resp_pair.status_code == 200
    assert resp_pair.json()["id"] == comp_id

    # 4. Error on nonexistent manual version
    resp_err = client.post(
        "/comparisons",
        json={"v1_version_id": "v1", "v2_version_id": "v99"},
    )
    assert resp_err.status_code == 404


def test_selection_and_staleness_endpoints(client: TestClient):
    """Verifies POST /selections and GET /selections/{id}/staleness."""
    # 1. Create selection for Section 2.1.1.1 in v1
    resp = client.post(
        "/selections",
        json={"version_id": "v1", "section_number": "2.1.1.1", "metadata": {"author": "qa_team"}},
    )
    assert resp.status_code == 201
    sel = resp.json()
    sel_id = sel["id"]
    assert sel["version_id"] == "v1"
    assert sel["section_number"] == "2.1.1.1"
    assert sel["status"] == "pending"
    assert len(sel["source_content_hash"]) == 64

    # 2. Check staleness against source version v1 (must be current)
    resp_stale_v1 = client.get(f"/selections/{sel_id}/staleness?target_version=v1")
    assert resp_stale_v1.status_code == 200
    assert resp_stale_v1.json()["is_stale"] is False

    # 3. Check staleness against v2 (Section 2.1.1.1 was modified in v2, must be stale)
    resp_stale_v2 = client.get(f"/selections/{sel_id}/staleness?target_version=v2")
    assert resp_stale_v2.status_code == 200
    stale_v2 = resp_stale_v2.json()
    assert stale_v2["is_stale"] is True
    assert "Content changed" in stale_v2["reason"]

    # 4. Check unchanged section across versions (Section 1)
    resp_sec1 = client.post("/selections", json={"version_id": "v1", "section_number": "1"})
    sel1_id = resp_sec1.json()["id"]
    resp_sec1_v2 = client.get(f"/selections/{sel1_id}/staleness?target_version=v2")
    assert resp_sec1_v2.status_code == 200
    assert resp_sec1_v2.json()["is_stale"] is False

    # 5. Error on selection for nonexistent section
    resp_err = client.post("/selections", json={"version_id": "v1", "section_number": "99.9"})
    assert resp_err.status_code == 404


def test_generate_qa_contract_reporting(client: TestClient):
    """
    Verifies that POST /selections/{id}/generate-qa returns 501 Not Implemented
    with an informative error message explaining that Step 6 is scheduled next.
    """
    # Create selection
    resp_sel = client.post("/selections", json={"version_id": "v1", "section_number": "3.2"})
    sel_id = resp_sel.json()["id"]

    # Call generate-qa
    resp_gen = client.post(
        f"/selections/{sel_id}/generate-qa",
        json={"num_questions": 3, "model": "gpt-4"},
    )
    assert resp_gen.status_code == 501
    assert "not yet implemented (scheduled for Step 6)" in resp_gen.json()["detail"]

    # 404 for nonexistent selection
    resp_404 = client.post("/selections/nonexistent-id/generate-qa")
    assert resp_404.status_code == 404
