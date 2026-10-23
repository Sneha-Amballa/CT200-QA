"""
Pydantic API Request and Response Schemas.

Defines validated data structures for:
- System health
- Manual ingestion and version listing
- Section nodes and search queries
- Document comparisons and diff summaries
- QA selection creation, staleness checking, and QA generation contract
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Health Schema
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    app: str = "ct200-qa"
    version: str = "1.0.0"


# ---------------------------------------------------------------------------
# Manual Version Schemas
# ---------------------------------------------------------------------------

class ManualVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_id: str
    filename: str
    file_hash: str
    title: str
    total_pages: int
    total_sections: int
    ingested_at: Optional[datetime | str] = None
    source_metadata: Dict[str, Any] = Field(default_factory=dict)


class ManualListResponse(BaseModel):
    manuals: List[ManualVersionResponse]
    total: int


# ---------------------------------------------------------------------------
# Section Schemas
# ---------------------------------------------------------------------------

class SectionSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_id: str
    section_number: str
    title: str
    parent_number: Optional[str] = None
    hierarchy_level: int
    numbering_depth: int
    order_index: int
    page_references: List[int]
    content_hash: str
    flags: List[str] = Field(default_factory=list)
    table_count: int = 0
    body_block_count: int = 0


class SectionDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version_id: str
    section_number: str
    title: str
    parent_number: Optional[str] = None
    hierarchy_level: int
    numbering_depth: int
    order_index: int
    page_references: List[int]
    content_hash: str
    normalized_text: str
    raw_text: str
    body_blocks: List[Dict[str, Any]] = Field(default_factory=list)
    tables: List[Dict[str, Any]] = Field(default_factory=list)
    flags: List[str] = Field(default_factory=list)


class SectionListResponse(BaseModel):
    version_id: str
    total_sections: int
    sections: List[SectionSummaryResponse]


# ---------------------------------------------------------------------------
# Search Schemas
# ---------------------------------------------------------------------------

class SearchResultItem(BaseModel):
    section_number: str
    title: str
    page_references: List[int]
    content_hash: str
    matched_in: str  # "title" or "body"
    snippet: str


class SearchResponse(BaseModel):
    version_id: str
    query: str
    total_results: int
    results: List[SearchResultItem]


# ---------------------------------------------------------------------------
# Comparison Schemas
# ---------------------------------------------------------------------------

class ComparisonRequest(BaseModel):
    v1_version_id: str = Field(..., description="Base manual version (e.g. 'v1')")
    v2_version_id: str = Field(..., description="Target manual version (e.g. 'v2')")
    force: bool = Field(False, description="Re-run comparison even if previously persisted")


class SectionDiffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    comparison_id: int
    section_number: str
    title: str
    status: str  # "added", "removed", "modified", "unchanged"
    content_changed: bool
    page_changed: bool
    v1_pages: List[int]
    v2_pages: List[int]
    v1_content_hash: Optional[str] = None
    v2_content_hash: Optional[str] = None
    word_diff: Optional[str] = None
    table_diff: Optional[Dict[str, Any]] = None
    explanation: str = ""


class ComparisonResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    v1_version_id: str
    v2_version_id: str
    compared_at: Optional[datetime | str] = None
    summary: Dict[str, Any]
    substantive_changes: List[str] = Field(default_factory=list)
    section_diffs: List[SectionDiffResponse] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# QA Selection and Staleness Schemas
# ---------------------------------------------------------------------------

class SelectionCreateRequest(BaseModel):
    version_id: str = Field(..., description="Manual version ID (e.g. 'v1')")
    section_number: str = Field(..., description="Section number (e.g. '4.2')")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict)


class SelectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    version_id: str
    section_number: str
    section_title: str
    source_content_hash: str
    qa_result_id: Optional[str] = None
    status: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StalenessResponse(BaseModel):
    selection_id: str
    source_version_id: str
    target_version_id: str
    section_number: str
    section_title: str
    source_content_hash: str
    current_content_hash: Optional[str] = None
    is_stale: bool
    reason: str


# ---------------------------------------------------------------------------
# QA Generation Contract Schemas
# ---------------------------------------------------------------------------

class GenerateQARequest(BaseModel):
    num_questions: int = Field(3, ge=1, le=10, description="Number of questions to generate")
    model: Optional[str] = Field("default", description="LLM model identifier")
    temperature: Optional[float] = Field(0.2, ge=0.0, le=1.0)


class GenerateQAResponse(BaseModel):
    status: str
    message: str
    selection_id: str
    version_id: str
    section_number: str
