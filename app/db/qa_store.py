"""
QA Document Store Repository.

Provides an abstract interface and JSON-file implementation for storing
structured QA generation documents. Designed to be swapped with MongoDB
or other document stores without changing consuming code.
"""

from __future__ import annotations

import abc
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid


class BaseQADocumentStore(abc.ABC):
    """Abstract repository for storing and retrieving structured QA documents."""

    @abc.abstractmethod
    def save(self, document: Dict[str, Any]) -> str:
        """Saves a QA document and returns its unique document ID."""
        pass

    @abc.abstractmethod
    def get(self, qa_id: str) -> Optional[Dict[str, Any]]:
        """Retrieves a QA document by ID, or None if not found."""
        pass

    @abc.abstractmethod
    def list_all(
        self,
        version_id: Optional[str] = None,
        section_number: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists QA documents, optionally filtered by version or section."""
        pass

    @abc.abstractmethod
    def delete(self, qa_id: str) -> bool:
        """Deletes a QA document by ID. Returns True if deleted, False if not found."""
        pass


class JSONFileQAStore(BaseQADocumentStore):
    """
    JSON file-backed repository for structured QA generation documents.
    Stores each QA artifact as an individual JSON file under `base_dir`.
    """

    def __init__(self, base_dir: Optional[str | Path] = None):
        if base_dir is None:
            base_dir = Path(__file__).resolve().parent.parent.parent / "data" / "qa_store"
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _file_path(self, qa_id: str) -> Path:
        # Sanitize qa_id to prevent path traversal
        clean_id = "".join(c for c in qa_id if c.isalnum() or c in ("-", "_"))
        return self.base_dir / f"{clean_id}.json"

    def save(self, document: Dict[str, Any]) -> str:
        """
        Saves document to disk as JSON.
        If 'qa_id' or 'id' is not present, generates a new UUID.
        """
        qa_id = document.get("qa_id") or document.get("id")
        if not qa_id:
            qa_id = f"qa_{uuid.uuid4().hex[:12]}"
            document["qa_id"] = qa_id

        target_file = self._file_path(qa_id)
        # Write to temporary file first then replace for atomicity
        temp_file = target_file.with_suffix(".tmp")
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(document, f, indent=2, ensure_ascii=False)
        temp_file.replace(target_file)
        return qa_id

    def get(self, qa_id: str) -> Optional[Dict[str, Any]]:
        """Reads and parses a QA document by ID."""
        target_file = self._file_path(qa_id)
        if not target_file.exists():
            return None
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def list_all(
        self,
        version_id: Optional[str] = None,
        section_number: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Lists QA documents with optional filtering."""
        results: List[Dict[str, Any]] = []
        for file in self.base_dir.glob("*.json"):
            try:
                with open(file, "r", encoding="utf-8") as f:
                    doc = json.load(f)
                if version_id and doc.get("version_id") != version_id:
                    continue
                if section_number and doc.get("section_number") != section_number:
                    continue
                results.append(doc)
            except (json.JSONDecodeError, OSError):
                continue
        return results

    def delete(self, qa_id: str) -> bool:
        """Deletes a QA document."""
        target_file = self._file_path(qa_id)
        if target_file.exists():
            target_file.unlink()
            return True
        return False
