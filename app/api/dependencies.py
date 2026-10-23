"""
FastAPI Route Dependencies.

Provides dependency injection for:
- Database sessions
- Core services (IngestionService, ComparisonService, QAService)
"""

from __future__ import annotations

from typing import Generator
from fastapi import Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.comparison import ComparisonService
from app.services.ingestion import IngestionService
from app.services.qa import QAService


def get_db_session() -> Generator[Session, None, None]:
    """Dependency provider for database session."""
    yield from get_db()


def get_ingestion_service() -> IngestionService:
    """Dependency provider for IngestionService."""
    return IngestionService()


def get_comparison_service() -> ComparisonService:
    """Dependency provider for ComparisonService."""
    return ComparisonService()


def get_qa_service() -> QAService:
    """Dependency provider for QAService."""
    return QAService()
