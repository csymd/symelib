"""
DatabaseManager facade — composes connection, schema, documents, lists.
"""

from __future__ import annotations

from pathlib import Path

from symworx_elibrary.services.db.base import DatabaseBase
from symworx_elibrary.services.db.documents import DocumentsMixin
from symworx_elibrary.services.db.paper_lists import PaperListsMixin
from symworx_elibrary.services.db.schema import SchemaMixin


class DatabaseManager(SchemaMixin, DocumentsMixin, PaperListsMixin, DatabaseBase):
    """SQLite manager for document metadata and paper lists."""

    def __init__(self, db_path: Path):
        DatabaseBase.__init__(self, db_path)
        self.init_database()


__all__ = ["DatabaseManager"]
