"""
SQLite persistence for elib (split package).
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import sqlite3

from elib.models.metadata import (
    DocumentMetadata,
    MetadataIssue,
    MetadataSource,
    MetadataStatus,
    SearchField,
    SearchQuery,
    SearchResult,
    SortBy,
    SortOrder,
    classify_metadata_status,
    has_real_doi,
    is_synthetic_doi,
    is_synthetic_pmid,
    sort_sql_clause,
)
from elib.models.paper_list import PaperList, PaperListItem
from elib.models.reference import Reference
from elib.utils.logging import LoggerConfig, get_shared_logger

logger = get_shared_logger(LoggerConfig(name="db_manager"))

_DOCUMENTS_EXTRA_COLUMNS: list[tuple[str, str]] = [
    ("metadata_status", "TEXT NOT NULL DEFAULT 'pending'"),
    ("metadata_source", "TEXT"),
    ("metadata_checked_at", "TIMESTAMP"),
    ("metadata_issue", "TEXT DEFAULT 'unknown'"),
    ("metadata_detail", "TEXT"),
    ("text_extract_chars", "INTEGER"),
    ("source_path", "TEXT"),
    ("original_filename", "TEXT"),
]


class DatabaseBase:
    """Connection + row mapping."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        if self.db_path.parent and str(self.db_path.parent) not in ("", "."):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _row_to_metadata(self, row: sqlite3.Row) -> DocumentMetadata:
        data = dict(row)
        # Coerce bool-ish sqlite ints
        if "s3_synced" in data and data["s3_synced"] is not None:
            data["s3_synced"] = bool(data["s3_synced"])
        return DocumentMetadata(**data)
